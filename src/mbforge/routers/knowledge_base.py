"""Knowledge base search endpoints with SSE streaming."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..utils.logger import get_logger

logger = get_logger("mbforge.kb_router")

router = APIRouter()


@router.post("/search")
async def kb_search(body: dict) -> dict:
    query = body.get("query", "")
    top_k = body.get("top_k", 10)
    project_root = body.get("project_root", "")
    doc_id_filter = body.get("doc_id_filter")
    if not query or not project_root:
        return {"success": False, "results": []}
    try:
        from ..core.knowledge_base import search

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: search(query, project_root, top_k=top_k, doc_id_filter=doc_id_filter),
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error("KB search failed: %s", e)
        return {"success": False, "error": str(e), "results": []}


@router.get("/search/stream")
async def kb_search_stream(
    query: str = "", top_k: int = 10, project_root: str = ""
) -> StreamingResponse:
    """SSE streaming search results."""

    async def event_stream():
        if not query or not project_root:
            yield f"data: {json.dumps({'type': 'error', 'error': 'query and project_root required'})}\n\n"
            return

        try:
            from ..core.knowledge_base import search

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, lambda: search(query, project_root, top_k=top_k)
            )
            # Stream results in batches
            results = result.get("results", [])
            batch_size = 3
            for i in range(0, len(results), batch_size):
                batch = results[i : i + batch_size]
                yield f"data: {json.dumps({'type': 'results', 'results': batch, 'count': len(results)}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.05)
            yield f"data: {json.dumps({'type': 'done', 'total': len(results)})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/pages")
async def kb_get_pages(body: dict) -> dict:
    doc_id = body.get("doc_id", "")
    pages = body.get("pages")
    root = body.get("project_root", "")
    if not doc_id or not root:
        return {"success": False, "pages": []}
    try:
        from ..core.knowledge_base import get_document_pages

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: get_document_pages(root, doc_id, pages)
        )
        return {"success": True, "pages": result}
    except Exception as e:
        return {"success": False, "error": str(e), "pages": []}


@router.post("/structure")
async def kb_get_structure(body: dict) -> dict:
    doc_id = body.get("doc_id", "")
    root = body.get("project_root", "")
    if not doc_id or not root:
        return {"success": False, "structure": None}
    try:
        from ..core.knowledge_base import get_document_tree

        tree = get_document_tree(root, doc_id)
        return {"success": True, "structure": tree}
    except Exception as e:
        return {"success": False, "error": str(e)}
