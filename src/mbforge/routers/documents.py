"""Document CRUD endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from ..core.project import list_documents
from ..utils.helpers import load_json, save_json

router = APIRouter()


@router.post("/list")
async def doc_list(body: dict) -> dict:
    root = body.get("root", "")
    if not root:
        return {"success": False, "documents": []}
    docs = list_documents(root)
    return {"success": True, "documents": [d.model_dump() for d in docs]}


@router.post("/delete")
async def doc_delete(body: dict) -> dict:
    root = body.get("root", "")
    doc_id = body.get("doc_id", "")
    if not root or not doc_id:
        return {"success": False, "error": "root and doc_id required"}
    idx_path = Path(root) / ".mbforge" / "index.json"
    data = load_json(idx_path, [])
    data = [d for d in data if d.get("doc_id") != doc_id]
    save_json(idx_path, data)
    return {"success": True}


@router.post("/reingest")
async def doc_reingest(body: dict) -> dict:
    root = body.get("root", "")
    doc_id = body.get("doc_id", "")
    if not root or not doc_id:
        return {"success": False, "error": "root and doc_id required"}
    from ..pipeline.runner import run_pipeline
    import asyncio

    idx_path = Path(root) / ".mbforge" / "index.json"
    data = load_json(idx_path, [])
    doc_entry = next((d for d in data if d.get("doc_id") == doc_id), None)
    if not doc_entry:
        return {"success": False, "error": f"document {doc_id} not found"}
    pdf_path = doc_entry.get("file_path", "")
    if not pdf_path or not Path(pdf_path).exists():
        return {"success": False, "error": f"PDF not found: {pdf_path}"}

    try:
        await asyncio.to_thread(run_pipeline, pdf_path, root, doc_id)
        return {"success": True, "message": "reingest completed"}
    except Exception as e:
        return {"success": False, "error": str(e)}
