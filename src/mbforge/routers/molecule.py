"""Molecule CRUD endpoints — supports both library_root and project_root."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter

from ..models.molecule import (
    MoleculeCreateRequest,
    MoleculeDeleteRequest,
    MoleculeGetRequest,
    MoleculeListRequest,
    MoleculeSearchRequest,
    MoleculeStatsRequest,
    MoleculeUpdateRequest,
)
from ..utils.helpers import resolve_root
from ..utils.logger import get_logger

logger = get_logger("mbforge.molecule_router")

router = APIRouter()


def _get_db(body: dict | object) -> tuple:
    """Resolve root from body and return (root_str, DatabaseManager)."""
    b = body if isinstance(body, dict) else body.model_dump()
    root = resolve_root(b)
    if not root:
        raise ValueError("No root path provided (library_root or project_root)")
    from ..core.database import DatabaseManager
    return root, DatabaseManager.get(root)


@router.post("/list")
async def mol_list(body: MoleculeListRequest) -> dict:
    try:
        root, db = _get_db(body)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    with db.mol_conn() as conn:
        where = "WHERE 1=1"
        params: list = []
        if body.status:
            where += " AND status = ?"
            params.append(body.status)
        total = conn.execute(f"SELECT COUNT(*) FROM molecules {where}", params).fetchone()[0]
        offset = (body.page - 1) * body.page_size
        rows = conn.execute(
            f"SELECT * FROM molecules {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [body.page_size, offset],
        ).fetchall()
        items = [dict(r) for r in rows]
    return {"success": True, "items": items, "total": total}


@router.post("/search")
async def mol_search(body: MoleculeSearchRequest) -> dict:
    try:
        root, db = _get_db(body)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    with db.mol_conn() as conn:
        rows = conn.execute(
            "SELECT m.* FROM mol_search ms JOIN molecules m ON ms.rowid = m.rowid "
            "WHERE mol_search MATCH ? LIMIT ?",
            (body.query, body.top_k),
        ).fetchall()
        results = [dict(r) for r in rows]
    return {"success": True, "results": results}


@router.post("/get")
async def mol_get(body: MoleculeGetRequest) -> dict:
    try:
        root, db = _get_db(body)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    with db.mol_conn() as conn:
        row = conn.execute("SELECT * FROM molecules WHERE mol_id = ?", (body.mol_id,)).fetchone()
        if not row:
            return {"success": False, "error": "not found"}
        return {"success": True, "molecule": dict(row)}


@router.post("/create")
async def mol_create(body: MoleculeCreateRequest) -> dict:
    try:
        root, db = _get_db(body)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    mol_id = body.mol_id or str(uuid.uuid4())
    with db.mol_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO molecules (mol_id, smiles, esmiles, name, source_type, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (mol_id, body.smiles, body.esmiles, body.name, body.source_type, "active"),
        )
    return {"success": True, "mol_id": mol_id}


@router.put("/{mol_id}")
async def mol_update(mol_id: str, body: MoleculeUpdateRequest) -> dict:
    try:
        root, db = _get_db(body)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    fields = []
    params = []
    for key in ["name", "esmiles", "activity", "activity_type", "units", "status", "notes", "labels", "properties"]:
        val = getattr(body, key, None)
        if val is not None:
            fields.append(f"{key} = ?")
            if isinstance(val, (list, dict)):
                val = json.dumps(val)
            params.append(val)
    if not fields:
        return {"success": False, "error": "no fields to update"}
    params.append(mol_id)
    with db.mol_conn() as conn:
        conn.execute(f"UPDATE molecules SET {', '.join(fields)} WHERE mol_id = ?", params)
    return {"success": True}


@router.delete("/{mol_id}")
async def mol_delete(mol_id: str, body: MoleculeDeleteRequest) -> dict:
    try:
        root, db = _get_db(body)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    with db.mol_conn() as conn:
        conn.execute("DELETE FROM molecules WHERE mol_id = ?", (mol_id,))
    return {"success": True}


@router.post("/stats")
async def mol_stats(body: MoleculeStatsRequest) -> dict:
    try:
        root, db = _get_db(body)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    with db.mol_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM molecules").fetchone()[0]
        by_status = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM molecules GROUP BY status"
        ).fetchall()
        by_source = conn.execute(
            "SELECT source_type, COUNT(*) as cnt FROM molecules GROUP BY source_type"
        ).fetchall()
    return {
        "success": True,
        "total": total,
        "by_status": {r["status"]: r["cnt"] for r in by_status},
        "by_source": {r["source_type"]: r["cnt"] for r in by_source},
    }
