"""Document CRUD endpoints — supports both library_root and project_root."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from ..core.library import LibraryStore
from ..pipeline.runner import run_pipeline
from ..utils.helpers import resolve_root
from ..utils.logger import get_logger

logger = get_logger("mbforge.documents_router")

router = APIRouter()


@router.post("/list")
async def doc_list(body: dict) -> dict:
    root = resolve_root(body)
    if not root:
        return {"success": False, "documents": []}
    store = LibraryStore.get(root)
    docs = store.list_documents()
    return {"success": True, "documents": [d.model_dump() for d in docs]}


@router.post("/delete")
async def doc_delete(body: dict) -> dict:
    root = resolve_root(body)
    doc_id = body.get("doc_id", "")
    if not root or not doc_id:
        return {"success": False, "error": "root and doc_id required"}
    store = LibraryStore.get(root)
    store.delete_document(doc_id)
    return {"success": True}


@router.post("/reingest")
async def doc_reingest(body: dict) -> dict:
    root = resolve_root(body)
    doc_id = body.get("doc_id", "")
    if not root or not doc_id:
        return {"success": False, "error": "root and doc_id required"}
    store = LibraryStore.get(root)
    file_path = store.resolve_file(doc_id)
    if not file_path:
        return {"success": False, "error": f"document {doc_id} not found"}
    try:
        await asyncio.to_thread(run_pipeline, file_path, root, doc_id)
        return {"success": True, "message": "reingest completed"}
    except Exception as e:
        return {"success": False, "error": str(e)}
