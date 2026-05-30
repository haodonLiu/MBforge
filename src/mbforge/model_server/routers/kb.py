"""知识库路由."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pathlib import Path
from pydantic import BaseModel

from ...core.knowledge_base import KnowledgeBase
from ...core.project import Project
from ...utils.logger import get_logger
from ..dependencies import get_project_from_root
from ..models.embedder import get_embedder

logger = get_logger(__name__)
router = APIRouter()


class SearchRequest(BaseModel):
    project_root: str
    query: str
    top_k: int = 5


class SectionData(BaseModel):
    title: str
    path: str
    text: str
    page_start: int | None = None
    page_end: int | None = None


class IndexSectionsRequest(BaseModel):
    project_root: str
    doc_id: str
    sections: list[SectionData]
    filename: str = ""


@router.post("/search")
async def kb_search(
    req: SearchRequest,
) -> dict:
    try:
        project = Project.open(Path(req.project_root))
        if project is None:
            return {"success": False, "error": f"Not a valid project: {req.project_root}"}
        kb = KnowledgeBase(project.root, embedder=get_embedder())
        results = kb.search(req.query, top_k=req.top_k)
        return {"success": True, "results": results}
    except Exception as e:
        logger.error(f"KB search failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/index-sections")
async def kb_index_sections(
    req: IndexSectionsRequest,
) -> dict:
    """索引 SectionChunk 列表到知识库（从 Rust pipeline 调用）."""
    try:
        project = Project.open(Path(req.project_root))
        if project is None:
            return {"success": False, "error": f"Not a valid project: {req.project_root}"}

        kb = KnowledgeBase(project.root, embedder=get_embedder())

        # 构建 ExtractedContent 兼容结构
        from ...core.types import ExtractedContent
        content = ExtractedContent()
        content.text = "\n\n".join(s.text for s in req.sections)
        content.chunks = [s.text for s in req.sections]
        content.metadata["source"] = req.filename
        content.metadata["doc_id"] = req.doc_id

        # 构建 sections 兼容结构
        from ...core.document_tree import SectionChunk
        content.sections = [
            SectionChunk(
                title=s.title,
                path=s.path,
                text=s.text,
                page_start=s.page_start,
                page_end=s.page_end,
                line_start=0,
                line_end=0,
            )
            for s in req.sections
        ]

        kb.index_document(req.doc_id, content, content.metadata)
        return {"success": True, "indexed": len(req.sections)}
    except Exception as e:
        logger.error(f"KB index-sections failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/stats")
async def kb_stats(
    project_root: str,
    project: Project = Depends(get_project_from_root),
) -> dict:
    try:
        kb = KnowledgeBase(project.root)
        stats = kb.get_stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        logger.error(f"KB stats failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
