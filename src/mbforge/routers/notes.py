"""Notes endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.post("/get")
async def notes_get(body: dict) -> dict:
    doc_id = body.get("doc_id", "")
    root = body.get("project_root", "")
    if not doc_id or not root:
        return {"success": True, "notes": ""}
    from pathlib import Path
    notes_path = Path(root) / "projects" / doc_id / "notes.md"
    if notes_path.exists():
        return {"success": True, "notes": notes_path.read_text(encoding="utf-8")}
    return {"success": True, "notes": ""}


@router.post("/save")
async def notes_save(body: dict) -> dict:
    doc_id = body.get("doc_id", "")
    root = body.get("project_root", "")
    content = body.get("content", "")
    if not doc_id or not root:
        return {"success": False, "error": "doc_id and project_root required"}
    from pathlib import Path

    from ..utils.helpers import ensure_dir
    notes_dir = Path(root) / "projects" / doc_id
    ensure_dir(notes_dir)
    (notes_dir / "notes.md").write_text(content, encoding="utf-8")
    return {"success": True}
