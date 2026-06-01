"""知识库路由 — 搜索和统计（浏览器 dev 模式 fallback）.

注意: 主搜索路径已迁移到 Rust Tauri command (kb_search / kb_search_stream)。
此路由仅作为浏览器开发模式的 fallback。
索引已完全由 Rust FTS5 处理，不再需要 /index-sections 端点。
"""

from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Depends
from pathlib import Path
from pydantic import BaseModel

from ...core.knowledge_base import KnowledgeBase
from ...core.project import Project
from ...utils.exceptions import ProjectNotValidError
from ...utils.logger import get_logger
from ..dependencies import get_project_from_root
from ..models.embedder import get_embedder

logger = get_logger(__name__)
router = APIRouter()


class SearchRequest(BaseModel):
    project_root: str
    query: str
    top_k: int = 5


@router.post("/search")
async def kb_search(req: SearchRequest) -> dict[str, Any]:
    """浏览器 dev 模式 fallback — 主路径使用 Rust Tauri command."""
    project = Project.open(Path(req.project_root))
    if project is None:
        raise ProjectNotValidError(f"Not a valid project: {req.project_root}")
    kb = KnowledgeBase(project.root, embedder=get_embedder())
    results = kb.search(req.query, top_k=req.top_k)
    return {"success": True, "results": results}


@router.get("/stats")
async def kb_stats(
    project_root: str,
    project: Project = Depends(get_project_from_root),
) -> dict[str, Any]:
    kb = KnowledgeBase(project.root)
    stats = kb.get_stats()
    return {"success": True, "stats": stats}
