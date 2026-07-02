"""Notes endpoints."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

from ..utils.helpers import ensure_dir, validate_project_root

router = APIRouter()

NOTES_INDEX = "notes_index.json"


def _notes_dir(root: str) -> Path:
    root_path = validate_project_root(root)
    return root_path / ".mbforge" / "notes"


def _index_path(root: str) -> Path:
    return _notes_dir(root) / NOTES_INDEX


def _load_index(root: str) -> list[dict]:
    p = _index_path(root)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Failed to load notes index: %s", e)
            return []
    return []


def _save_index(root: str, index: list[dict]) -> None:
    ensure_dir(_notes_dir(root))
    _index_path(root).write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


@router.post("/list")
async def notes_list(body: dict) -> dict:
    root = body.get("projectRoot", "") or body.get("project_root", "")
    if not root:
        return {"success": True, "notes": []}
    validate_project_root(root)
    return {"success": True, "notes": _load_index(root)}


@router.post("/get")
async def notes_get(body: dict) -> dict:
    note_id = body.get("id", "") or body.get("doc_id", "")
    root = body.get("projectRoot", "") or body.get("project_root", "")
    if not note_id or not root:
        return {"success": True, "notes": ""}
    validate_project_root(root)
    notes_path = _notes_dir(root) / f"{note_id}.md"
    if notes_path.exists():
        return {"success": True, "notes": notes_path.read_text(encoding="utf-8")}
    return {"success": True, "notes": ""}


@router.post("/save")
async def notes_save(body: dict) -> dict:
    root = body.get("projectRoot", "") or body.get("project_root", "")
    note = body.get("note", {})
    if not root or not note:
        return {"success": False, "error": "projectRoot and note required"}
    note_id = note.get("id", "")
    if not note_id:
        return {"success": False, "error": "note.id required"}
    validate_project_root(root)
    # 保存笔记内容
    ensure_dir(_notes_dir(root))
    notes_path = _notes_dir(root) / f"{note_id}.md"
    notes_path.write_text(note.get("content", ""), encoding="utf-8")
    # 更新索引
    index = _load_index(root)
    entry = {
        "id": note_id,
        "title": note.get("title", ""),
        "tags": note.get("tags", []),
        "links": note.get("links", []),
        "createdAt": note.get("createdAt", ""),
        "updatedAt": note.get("updatedAt", ""),
    }
    existing = next((i for i, n in enumerate(index) if n.get("id") == note_id), None)
    if existing is not None:
        index[existing] = entry
    else:
        index.append(entry)
    _save_index(root, index)
    return {"success": True, "note": entry}


@router.post("/delete")
async def notes_delete(body: dict) -> dict:
    root = body.get("projectRoot", "") or body.get("project_root", "")
    note_id = body.get("id", "")
    if not root or not note_id:
        return {"success": False, "error": "root and note_id required"}
    validate_project_root(root)
    notes_path = _notes_dir(root) / f"{note_id}.md"
    if notes_path.exists():
        notes_path.unlink()
    index = _load_index(root)
    index = [n for n in index if n.get("id") != note_id]
    _save_index(root, index)
    return {"success": True}


@router.post("/backlinks")
async def notes_backlinks(body: dict) -> dict:
    root = body.get("projectRoot", "") or body.get("project_root", "")
    target_id = body.get("targetId", "")
    if not root or not target_id:
        return {"success": True, "backlinks": []}
    validate_project_root(root)
    index = _load_index(root)
    result = []
    for note in index:
        for link in note.get("links", []):
            if link.get("refId") == target_id:
                result.append(note)
                break
    return {"success": True, "backlinks": result}
