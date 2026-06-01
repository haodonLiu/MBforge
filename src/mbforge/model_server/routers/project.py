"""项目路由 (Browser dev fallback).

这些端点仅在前端以纯浏览器模式运行时作为降级使用。
项目打开/扫描/创建的主路径已在 Rust (Tauri) 中实现。
"""

from __future__ import annotations
from typing import Any

from pathlib import Path

from fastapi import APIRouter

from ...core.project import Project
from ...utils.constants import PROJECT_META_DIR
from ...utils.logger import get_logger
from ..dependencies import get_project_from_root

logger = get_logger(__name__)
router = APIRouter()


def _project_to_dict(project: Project) -> dict[str, Any]:
    """Format project metadata for API response."""
    docs = project.list_documents()
    return {
        "name": project.name,
        "root": str(project.root),
        "document_count": len(docs),
        "molecule_count": 0,
        "indexed_count": sum(1 for d in docs if d.indexed),
    }


@router.get("/list")
async def list_documents(root: str) -> dict[str, Any]:
    try:
        project = await get_project_from_root(root)
        docs = project.list_documents()
        return {
            "success": True,
            "documents": [
                {
                    "doc_id": d.doc_id,
                    "path": str(d.path),
                    "doc_type": d.doc_type,
                    "title": d.title,
                    "indexed": d.indexed,
                }
                for d in docs
            ],
        }
    except Exception as e:
        logger.error(f"List documents failed for root={root}: {e}", exc_info=True)
        return {"success": False, "error": f"列出文档失败: {e}"}



def _build_file_tree(root: Path) -> list[dict]:
    """Recursively build a file tree from a directory, excluding hidden and meta dirs."""
    result: list[dict] = []
    try:
        entries = sorted(root.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return result

    for entry in entries:
        # Skip hidden files/dirs and .mbforge meta directory
        if entry.name.startswith("."):
            continue
        if entry.name == PROJECT_META_DIR:
            continue
        if entry.is_dir():
            children = _build_file_tree(entry)
            result.append({
                "name": entry.name,
                "path": str(entry),
                "is_dir": True,
                "children": children,
            })
        else:
            result.append({
                "name": entry.name,
                "path": str(entry),
                "is_dir": False,
                "children": [],
            })
    return result


@router.get("/file-tree")
async def file_tree(root: str) -> dict[str, Any]:
    try:
        project = Project.open(Path(root))
        if project is None:
            return {"success": False, "error": f"Not a valid project: {root}"}
        tree = _build_file_tree(project.root)
        return {"success": True, "tree": tree}
    except Exception as e:
        logger.error(f"File tree failed for root={root}: {e}", exc_info=True)
        return {"success": False, "error": f"获取文件树失败: {e}"}
