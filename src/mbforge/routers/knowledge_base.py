"""Knowledge base search endpoints with SSE streaming."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse

from ..utils.logger import get_logger

logger = get_logger("mbforge.kb_router")

router = APIRouter()


def _resolve_wiki_root(library_root: str) -> Path:
    if not library_root:
        raise HTTPException(400, "library_root required")
    root = Path(library_root).resolve()
    try:
        from ..utils.config import load_global_config

        configured_root = load_global_config().library_root or str(Path.home() / "mbforge")
        configured = Path(configured_root).resolve()
        root.relative_to(configured)
    except ValueError as exc:
        raise HTTPException(400, "library_root not within configured library") from exc
    except Exception:
        if not root.is_absolute():
            raise HTTPException(400, "library_root must be absolute") from None
    return root


@router.post("/search")
async def kb_search(body: dict) -> dict:
    query = body.get("query", "")
    top_k = body.get("top_k", 10)
    library_root = body.get("library_root", "")
    doc_id_filter = body.get("doc_id_filter")
    if not query or not library_root:
        return {"success": False, "results": []}
    try:
        from ..core.knowledge_base import search

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: search(query, library_root, top_k=top_k, doc_id_filter=doc_id_filter),
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error("KB search failed: %s", e)
        return {"success": False, "error": str(e), "results": []}


@router.get("/search/stream")
async def kb_search_stream(
    query: str = "", top_k: int = 10, library_root: str = ""
) -> StreamingResponse:
    """SSE streaming search results."""

    async def event_stream():
        if not query or not library_root:
            yield f"data: {json.dumps({'type': 'error', 'error': 'query and library_root required'})}\n\n"
            return

        try:
            from ..core.knowledge_base import search

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, lambda: search(query, library_root, top_k=top_k)
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
    root = body.get("library_root", "")
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
    root = body.get("library_root", "")
    if not doc_id or not root:
        return {"success": False, "structure": None}
    try:
        from ..core.knowledge_base import get_document_tree

        tree = get_document_tree(root, doc_id)
        return {"success": True, "structure": tree}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Wiki artifact endpoints — serve summaries/concepts/entities produced
# by the OpenKB wiki compilation step. Used by the frontend WikiDrawer.
# ---------------------------------------------------------------------------


def _safe_wiki_basename(value: str) -> str:
    safe = Path(value).name
    if not safe or safe != value:
        raise HTTPException(400, f"invalid wiki identifier: {value}")
    return safe


@router.get("/wiki/summary")
async def kb_get_wiki_summary(doc_id: str = "", library_root: str = "") -> PlainTextResponse:
    """Return wiki summary markdown for a document."""
    if not doc_id:
        raise HTTPException(400, "doc_id required")
    root = _resolve_wiki_root(library_root)
    safe_doc_id = _safe_wiki_basename(doc_id)
    p = root / ".mbforge" / "openkb" / "wiki" / "summaries" / f"{safe_doc_id}.md"
    if not p.is_file():
        raise HTTPException(404, f"wiki summary not found for {doc_id}")
    return PlainTextResponse(p.read_text(encoding="utf-8"))


@router.get("/wiki/concept")
async def kb_get_wiki_concept(name: str = "", library_root: str = "") -> PlainTextResponse:
    """Return a single concept page markdown by concept name."""
    if not name:
        raise HTTPException(400, "name required")
    root = _resolve_wiki_root(library_root)
    safe_name = _safe_wiki_basename(name)
    p = root / ".mbforge" / "openkb" / "wiki" / "concepts" / f"{safe_name}.md"
    if not p.is_file():
        raise HTTPException(404, f"concept not found: {name}")
    return PlainTextResponse(p.read_text(encoding="utf-8"))


@router.get("/wiki/entity")
async def kb_get_wiki_entity(name: str = "", library_root: str = "") -> PlainTextResponse:
    """Return a single entity page markdown by entity name."""
    if not name:
        raise HTTPException(400, "name required")
    root = _resolve_wiki_root(library_root)
    safe_name = _safe_wiki_basename(name)
    p = root / ".mbforge" / "openkb" / "wiki" / "entities" / f"{safe_name}.md"
    if not p.is_file():
        raise HTTPException(404, f"entity not found: {name}")
    return PlainTextResponse(p.read_text(encoding="utf-8"))


@router.get("/wiki/list")
async def kb_list_wiki(library_root: str = "") -> dict:
    """List all wiki artifacts (summaries/concepts/entities) for the drawer."""
    root = _resolve_wiki_root(library_root)
    wiki = root / ".mbforge" / "openkb" / "wiki"

    def _list(sub: str) -> list[str]:
        d = wiki / sub
        if not d.exists():
            return []
        return sorted(p.stem for p in d.glob("*.md") if p.is_file())

    return {
        "summaries": _list("summaries"),
        "concepts": _list("concepts"),
        "entities": _list("entities"),
    }
