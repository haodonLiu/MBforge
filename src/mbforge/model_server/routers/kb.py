"""知识库路由."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ...core.knowledge_base import KnowledgeBase
from ...core.project import Project
from ..models.embedder import get_embedder

router = APIRouter()


class SearchRequest(BaseModel):
    project_root: str
    query: str
    top_k: int = 5


@router.post("/search")
async def kb_search(req: SearchRequest) -> dict:
    try:
        project = Project.open(Path(req.project_root))
        if project is None:
            return {"success": False, "error": "Not a valid project"}

        kb = KnowledgeBase(project.root, embedder=get_embedder())
        results = kb.search(req.query, top_k=req.top_k)
        return {"success": True, "results": results}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/stats")
async def kb_stats(project_root: str) -> dict:
    try:
        project = Project.open(Path(project_root))
        if project is None:
            return {"success": False, "error": "Not a valid project"}

        kb = KnowledgeBase(project.root)
        stats = kb.get_stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        return {"success": False, "error": str(e)}
