"""Notes endpoints — supports both library_root and project_root."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

from ..utils.helpers import ensure_dir, resolve_root
from ..utils.logger import get_logger

logger = get_logger("mbforge.notes_router")

router = APIRouter()

NOTES_INDEX = "notes_index.json"


def _notes_root(body: dict) -> Path:
    root = resolve_root(body)
    if not root:
        raise ValueError("No root path provided")
    return Path(root) / ".mbforge" / "notes"


def _index_path(body: dict) -> Path:
    return _notes_root(body) / NOTES_INDEX


def _load_index(body: dict) -> list[dict]:
    p = _index_path(body)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Failed to load notes index: %s", e)
        return []


def _save_index(body: dict, index: list[dict]) -> None:
    notes_dir = _notes_root(body)
    ensure_dir(notes_dir)
    _index_path(body).write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


@router.post("/list")
async def notes_list(body: dict) -> dict:
    try:
        return {"success": True, "notes": _load_index(body)}
    except ValueError:
        return {"success": True, "notes": []}


@router.post("/get")
async def notes_get(body: dict) -> dict:
    note_id = body.get("id", "") or body.get("doc_id", "")
    if not note_id:
        return {"success": True, "notes": ""}
    try:
        notes_path = _notes_root(body) / f"{note_id}.md"
        if notes_path.exists():
            return {"success": True, "notes": notes_path.read_text(encoding="utf-8")}
        return {"success": True, "notes": ""}
    except ValueError:
        return {"success": True, "notes": ""}


@router.post("/save")
async def notes_save(body: dict) -> dict:
    note = body.get("note", {})
    note_id = note.get("id", "") if isinstance(note, dict) else ""
    if not note_id:
        return {"success": False, "error": "note.id required"}
    try:
        notes_dir = _notes_root(body)
        ensure_dir(notes_dir)
        notes_path = notes_dir / f"{note_id}.md"
        notes_path.write_text(note.get("content", ""), encoding="utf-8")
        index = _load_index(body)
        entry = {
            "id": note_id,
            "title": note.get("title", ""),
            "tags": note.get("tags", []),
            "links": note.get("links", []),
            "createdAt": note.get("createdAt", ""),
            "updatedAt": note.get("updatedAt", ""),
        }
        existing = next((i for i, e in enumerate(index) if e.get("id") == note_id), None)
        if existing is not None:
            index[existing] = entry
        else:
            index.append(entry)
        _save_index(body, index)
        return {"success": True, "note": entry}
    except ValueError as e:
        return {"success": False, "error": str(e)}


@router.post("/delete")
async def notes_delete(body: dict) -> dict:
    note_id = body.get("id", "")
    if not note_id:
        return {"success": False, "error": "id required"}
    try:
        notes_dir = _notes_root(body)
        notes_path = notes_dir / f"{note_id}.md"
        if notes_path.exists():
            notes_path.unlink()
        index = _load_index(body)
        index = [n for n in index if n.get("id") != note_id]
        _save_index(body, index)
        return {"success": True}
    except ValueError as e:
        return {"success": False, "error": str(e)}


@router.post("/backlinks")
async def notes_backlinks(body: dict) -> dict:
    target_id = body.get("targetId", "")
    if not target_id:
        return {"success": True, "backlinks": []}
    try:
        index = _load_index(body)
        result = [n for n in index if target_id in str(n.get("links", []))]
        return {"success": True, "backlinks": result}
    except ValueError:
        return {"success": True, "backlinks": []}
