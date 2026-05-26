"""Zotero Bridge HTTP 请求处理器."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

from aiohttp import web

from ..core.document import ExtractedContent
from ..core.knowledge_base import KnowledgeBase
from ..core.mol_database import MoleculeDatabase
from ..core.project import Project
from ..models import create_embedder_from_config, create_llm_from_config
from ..parsers.pdf_parser import PDFParserPipeline
from ..utils.config import load_global_config
from ..utils.constants import PROJECT_META_DIR
from ..utils.helpers import generate_uuid
from ..utils.logger import get_logger
from .models import ImportRequest, ImportResult

logger = get_logger(__name__)


async def health(request: web.Request) -> web.Response:
    """健康检查."""
    return web.json_response({"status": "ok", "service": "mbforge-zotero-bridge"})


async def import_items(request: web.Request) -> web.Response:
    """接收 Zotero 推送的条目并导入项目."""
    project_root: Path = request.app["project_root"]
    body = await request.json()
    req = ImportRequest.model_validate(body)

    imported = 0
    failed = 0
    results: list[ImportResult] = []

    project = Project.open(project_root)
    if project is None:
        project = Project.create(project_root)

    for item in req.items:
        try:
            result = await _import_single_item(request.app, project, item, req.auto_index)
            if result.status == "imported":
                imported += 1
            results.append(result)
        except Exception as exc:
            logger.exception("导入 Zotero 条目失败: %s", item.key)
            failed += 1
            results.append(
                ImportResult(
                    zotero_key=item.key,
                    status="error",
                    message=str(exc),
                )
            )

    return web.json_response(
        {
            "imported": imported,
            "failed": failed,
            "results": [r.model_dump() for r in results],
        }
    )


async def _import_single_item(
    app: web.Application,
    project: Project,
    item,
    auto_index: bool,
) -> ImportResult:
    """导入单个 Zotero 条目.

    流程：
    1. 找第一个可用的 PDF 附件
    2. 复制到项目目录（命名：{zotero_key}_{filename}）
    3. 保存 annotations 到 .mbforge/zotero_annotations/
    4. 加入项目索引
    5. 如 auto_index=True，后台调用 PDFParserPipeline
    """
    pdf_attachment = None
    for att in item.attachments:
        if att.contentType == "application/pdf" and Path(att.path).exists():
            pdf_attachment = att
            break

    if pdf_attachment is None:
        return ImportResult(
            zotero_key=item.key,
            status="skipped",
            message="未找到可用的 PDF 附件",
        )

    # 目标路径：项目根 / zotero_imports / {key}_{filename}
    dest_dir = project.root / "zotero_imports"
    dest_dir.mkdir(exist_ok=True)
    safe_name = f"{item.key}_{pdf_attachment.filename}"
    dest_path = dest_dir / safe_name

    # 复制文件（异步跑在 executor 里避免阻塞事件循环）
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, shutil.copy2, pdf_attachment.path, dest_path)

    # 保存 annotations
    if item.annotations:
        anno_dir = project.meta_dir / "zotero_annotations"
        anno_dir.mkdir(parents=True, exist_ok=True)
        anno_path = anno_dir / f"{item.key}.json"
        anno_data = {
            "zotero_key": item.key,
            "title": item.title,
            "doi": item.doi,
            "annotations": [a.model_dump() for a in item.annotations],
        }
        await loop.run_in_executor(
            None, _write_json, anno_path, anno_data
        )

    # 加入项目索引
    entry = project.add_file(dest_path)

    # 可选：自动解析索引（在 executor 中执行，避免阻塞 HTTP）
    if auto_index:
        await loop.run_in_executor(
            None, _run_indexing, app, project.root, dest_path, entry.doc_id
        )
        entry.indexed = True
        project._save_index()

    return ImportResult(
        zotero_key=item.key,
        status="imported",
        doc_id=entry.doc_id,
        path=str(dest_path),
        message="已导入" + ("并索引" if auto_index else ""),
    )


def _write_json(path: Path, data: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _run_indexing(
    app: web.Application,
    project_root: Path,
    pdf_path: Path,
    doc_id: str,
) -> None:
    """同步执行 PDF 解析和索引（在后台线程中运行）."""
    try:
        config = load_global_config()
        embedder = create_embedder_from_config(config.embed)
        llm = create_llm_from_config(config.llm)
        kb = KnowledgeBase(project_root, embedder=embedder)
        mol_db = MoleculeDatabase(project_root)

        pipeline = PDFParserPipeline(
            llm=llm,
            embedder=embedder,
            knowledge_base=kb,
            mol_db=mol_db,
        )
        pipeline.parse(pdf_path, doc_id=doc_id)
        logger.info("Zotero 导入文件索引完成: %s", pdf_path.name)
    except Exception:
        logger.exception("Zotero 导入文件索引失败: %s", pdf_path.name)
