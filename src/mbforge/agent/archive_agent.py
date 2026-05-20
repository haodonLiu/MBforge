"""归档 Agent — 后台专职读取、整理、归档已处理文件.

处理完文件后自动运行：
1. 扫描 output/ 中已处理的文件
2. 检查 RAG 索引状态，未索引的补索引
3. 用 LLM 生成/补充摘要和标签
4. 更新 TODO 条目的归档状态
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..core.document import ExtractedContent
from ..core.todo_manager import TodoManager, TodoStatus
from ..utils.helpers import split_text_chunks
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ArchiveAgent:
    """归档 Agent — 读取、整理、归档已处理文件."""

    def __init__(
        self,
        llm=None,
        knowledge_base=None,
        mol_db=None,
        project_root: Optional[Path] = None,
    ):
        self.llm = llm
        self.kb = knowledge_base
        self.mol_db = mol_db
        self.project_root = Path(project_root).resolve() if project_root else None
        self._running = False

    def run(self) -> Dict[str, Any]:
        """执行归档整理，返回统计信息."""
        if self.project_root is None:
            return {"error": "No project root"}

        todo = TodoManager(self.project_root)
        done_entries = [e for e in todo.get_all() if e.status == TodoStatus.DONE]

        stats = {"total": len(done_entries), "indexed": 0, "summarized": 0, "skipped": 0}

        for entry in done_entries:
            out_dir = Path(entry.output_dir) if entry.output_dir else todo.get_output_path(entry.doc_id)
            if not out_dir.exists():
                stats["skipped"] += 1
                continue

            try:
                result = self._archive_file(entry, out_dir)
                if result.get("indexed"):
                    stats["indexed"] += 1
                if result.get("summarized"):
                    stats["summarized"] += 1
            except Exception as e:
                logger.warning(f"Archive failed for {entry.filename}: {e}")
                stats["skipped"] += 1

        logger.info(f"Archive complete: {stats}")
        return stats

    def run_async(self, on_done: Optional[Callable[[], None]] = None) -> None:
        """异步执行归档."""
        if self._running:
            return

        def _worker():
            self._running = True
            try:
                self.run()
            finally:
                self._running = False
                if on_done:
                    on_done()

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def _archive_file(self, entry, out_dir: Path) -> Dict[str, Any]:
        """归档单个文件."""
        result: Dict[str, Any] = {"indexed": False, "summarized": False}

        index_path = out_dir / "index.json"
        if not index_path.exists():
            return result

        with open(index_path, "r", encoding="utf-8") as f:
            index_data = json.load(f)

        # 1. 确保已索引到知识库
        if self.kb is not None and not index_data.get("rag_indexed"):
            self._ensure_rag_indexed(entry, out_dir, index_data)
            result["indexed"] = True

        # 2. 补充摘要（如果没有 LLM 生成的摘要）
        summary_path = out_dir / "summary.json"
        if self.llm is not None and not summary_path.exists():
            self._generate_summary(entry, out_dir, index_data)
            result["summarized"] = True

        return result

    def _ensure_rag_indexed(self, entry, out_dir: Path, index_data: dict) -> None:
        """确保文件内容已索引到 RAG 知识库."""
        content_path = out_dir / "content.json"
        if not content_path.exists():
            return

        with open(content_path, "r", encoding="utf-8") as f:
            content_data = json.load(f)

        text = content_data.get("text", "")
        if not text:
            return

        chunks = content_data.get("chunks", [])
        if not chunks:
            chunks = split_text_chunks(text)

        source = entry.source_path
        content = ExtractedContent(text=text, chunks=chunks)
        self.kb.index_document(entry.doc_id, content, metadata={"source": source})
        logger.info(f"RAG indexed: {entry.filename}")

    def _generate_summary(self, entry, out_dir: Path, index_data: dict) -> None:
        """用 LLM 生成文档摘要."""
        content_path = out_dir / "content.json"
        if not content_path.exists():
            return

        with open(content_path, "r", encoding="utf-8") as f:
            content_data = json.load(f)

        text = content_data.get("text", "")
        if not text or len(text) < 50:
            return

        from ..models.base import Message

        prompt = (
            "请对以下科学文献内容生成结构化摘要（不超过 1500 字），包含：\n"
            "1. 研究背景与目的\n"
            "2. 主要方法与实验设计\n"
            "3. 关键结果与发现\n"
            "4. 涉及的分子/化合物列表\n"
            "5. 生物活性数据摘要\n\n"
            f"内容：\n{text[:8000]}"
        )
        try:
            response = self.llm.chat([
                Message(role="system", content="你是一位专业的药物化学文献分析助手。"),
                Message(role="user", content=prompt),
            ])

            summary_data = {
                "doc_id": entry.doc_id,
                "filename": entry.filename,
                "l1_overview": response.strip(),
                "source": entry.source_path,
            }
            summary_path = out_dir / "summary.json"
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Summary generated: {entry.filename}")
        except Exception as e:
            logger.warning(f"Summary generation failed for {entry.filename}: {e}")
