"""Molecule CRUD endpoints."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter

from ..utils.logger import get_logger

logger = get_logger("mbforge.molecule_router")

router = APIRouter()


@router.post("/list")
async def mol_list(body: dict) -> dict:
    root = body.get("project_root", "")
    page = body.get("page", 1)
    page_size = body.get("page_size", 50)
    status = body.get("status", "")
    if not root:
        return {"success": False, "items": [], "total": 0}
    from ..core.database import DatabaseManager

    db = DatabaseManager.get(root)
    with db.mol_conn() as conn:
        where = "WHERE 1=1"
        params: list = []
        if status:
            where += " AND status = ?"
            params.append(status)
        total = conn.execute(f"SELECT COUNT(*) FROM molecules {where}", params).fetchone()[0]
        offset = (page - 1) * page_size
        rows = conn.execute(
            f"SELECT * FROM molecules {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()
        items = [dict(r) for r in rows]
    return {"success": True, "items": items, "total": total}


@router.post("/search")
async def mol_search(body: dict) -> dict:
    query = body.get("query", "")
    root = body.get("project_root", "")
    top_k = body.get("top_k", 20)
    if not query or not root:
        return {"success": False, "results": []}
    from ..core.database import DatabaseManager

    db = DatabaseManager.get(root)
    with db.mol_conn() as conn:
        rows = conn.execute(
            "SELECT m.* FROM mol_search ms JOIN molecules m ON ms.rowid = m.rowid "
            "WHERE mol_search MATCH ? LIMIT ?",
            (query, top_k),
        ).fetchall()
        results = [dict(r) for r in rows]
    return {"success": True, "results": results}


@router.post("/get")
async def mol_get(body: dict) -> dict:
    mol_id = body.get("mol_id", "")
    root = body.get("project_root", "")
    if not mol_id or not root:
        return {"success": False, "error": "mol_id and project_root required"}
    from ..core.database import DatabaseManager

    db = DatabaseManager.get(root)
    with db.mol_conn() as conn:
        row = conn.execute("SELECT * FROM molecules WHERE mol_id = ?", (mol_id,)).fetchone()
        if not row:
            return {"success": False, "error": "not found"}
        return {"success": True, "molecule": dict(row)}


@router.post("/create")
async def mol_create(body: dict) -> dict:
    root = body.get("project_root", "")
    smiles = body.get("smiles", "")
    if not root or not smiles:
        return {"success": False, "error": "project_root and smiles required"}
    mol_id = body.get("mol_id", str(uuid.uuid4()))
    from ..core.database import DatabaseManager

    db = DatabaseManager.get(root)
    with db.mol_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO molecules (mol_id, smiles, esmiles, name, source_type, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (mol_id, smiles, body.get("esmiles", ""), body.get("name", ""), body.get("source_type", "manual"), "active"),
        )
    return {"success": True, "mol_id": mol_id}


@router.put("/{mol_id}")
async def mol_update(mol_id: str, body: dict) -> dict:
    root = body.get("project_root", "")
    if not root:
        return {"success": False, "error": "project_root required"}
    from ..core.database import DatabaseManager

    db = DatabaseManager.get(root)
    fields = []
    params = []
    for key in ["name", "esmiles", "activity", "activity_type", "units", "status", "notes", "labels", "properties"]:
        if key in body:
            fields.append(f"{key} = ?")
            val = body[key]
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
async def mol_delete(mol_id: str, body: dict) -> dict:
    root = body.get("project_root", "")
    if not root:
        return {"success": False, "error": "project_root required"}
    from ..core.database import DatabaseManager

    db = DatabaseManager.get(root)
    with db.mol_conn() as conn:
        conn.execute("DELETE FROM molecules WHERE mol_id = ?", (mol_id,))
    return {"success": True}


@router.post("/stats")
async def mol_stats(body: dict) -> dict:
    root = body.get("project_root", "")
    if not root:
        return {"success": False}
    from ..core.database import DatabaseManager

    db = DatabaseManager.get(root)
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
