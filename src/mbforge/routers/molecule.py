"""Molecule CRUD endpoints."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter

from ..models.molecule import (
    MoleculeCreateRequest,
    MoleculeCreateResponse,
    MoleculeDeleteRequest,
    MoleculeDeleteResponse,
    MoleculeEvidenceRequest,
    MoleculeEvidenceResponse,
    MoleculeGetRequest,
    MoleculeGetResponse,
    MoleculeListRequest,
    MoleculeListResponse,
    MoleculeSearchRequest,
    MoleculeSearchResponse,
    MoleculeStatsRequest,
    MoleculeStatsResponse,
    MoleculeUpdateRequest,
    MoleculeUpdateResponse,
)
from ..utils.helpers import NotFoundError, ValidationError, resolve_root
from ..utils.logger import get_logger

logger = get_logger("mbforge.molecule_router")

router = APIRouter()


def _get_db(body: dict | object) -> tuple:
    """Resolve root from body and return (root_str, DatabaseManager)."""
    b = body if isinstance(body, dict) else body.model_dump()
    root = resolve_root(b)
    if not root:
        raise ValidationError("library_root is required")
    from ..core.database import DatabaseManager
    return root, DatabaseManager.get(root)


# Truncation limits for evidence lists returned per molecule.
_EVIDENCE_LIST_LIMIT = 50
_EVIDENCE_FULL_LIMIT = 100_000


@router.post("/list")
async def mol_list(body: MoleculeListRequest) -> MoleculeListResponse:
    root, db = _get_db(body)
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
        # Attach evidence chain (truncated for list view).
        items = _attach_evidence_batch(conn, root, items, limit=_EVIDENCE_LIST_LIMIT)
    return MoleculeListResponse(items=items, total=total)


def _attach_evidence_batch(
    conn, library_root: str, items: list[dict], limit: int = 50
) -> list[dict]:
    """Attach ``evidence`` list to each item by canonical_smiles.

    Sort order: kind, doc_id, page, id. Limit per molecule to keep the
    list response bounded. Use the dedicated ``/evidence`` endpoint for
    the full chain.
    """
    if not items:
        return items
    canonicals = sorted(
        {i.get("canonical_smiles") or i.get("mol_id") for i in items if i.get("mol_id")}
    )
    placeholders = ",".join("?" for _ in canonicals)
    rows = conn.execute(
        f"""
        SELECT id, canonical_smiles, doc_id, page,
               bbox_x0, bbox_y0, bbox_x1, bbox_y1, crop_relpath,
               context_text, code_text, role, kind, confidence, source_type,
               created_at
        FROM evidence
        WHERE canonical_smiles IN ({placeholders})
        ORDER BY canonical_smiles, kind, doc_id, page, id
        """,
        canonicals,
    ).fetchall()
    grouped: dict[str, list[dict]] = {cs: [] for cs in canonicals}
    for r in rows:
        d = dict(r)
        d["crop_url"] = _build_crop_url(library_root, d)
        grouped[d["canonical_smiles"]].append(d)
    for item in items:
        cs = item.get("canonical_smiles") or item.get("mol_id")
        ev = grouped.get(cs, [])
        item["evidence"] = ev[:limit]
        item["evidence_total"] = len(ev)
    return items


def _build_crop_url(library_root: str, ev_row: dict) -> str | None:
    """Return the crop image URL for an evidence row, or None if no crop."""
    if not ev_row.get("crop_relpath") or not ev_row.get("doc_id"):
        return None
    rel = Path(ev_row["crop_relpath"]).name
    return (
        f"/api/v1/library/documents/{ev_row['doc_id']}/crop"
        f"?rel_path={rel}&library_root={library_root}"
    )


@router.post("/search")
async def mol_search(body: MoleculeSearchRequest) -> MoleculeSearchResponse:
    root, db = _get_db(body)
    with db.mol_conn() as conn:
        rows = conn.execute(
            "SELECT m.* FROM mol_search ms JOIN molecules m ON ms.rowid = m.rowid "
            "WHERE mol_search MATCH ? LIMIT ?",
            (body.query, body.top_k),
        ).fetchall()
        results = [dict(r) for r in rows]
    return MoleculeSearchResponse(results=results)


@router.post("/get")
async def mol_get(body: MoleculeGetRequest) -> MoleculeGetResponse:
    root, db = _get_db(body)
    with db.mol_conn() as conn:
        row = conn.execute("SELECT * FROM molecules WHERE mol_id = ?", (body.mol_id,)).fetchone()
        if not row:
            raise NotFoundError("molecule not found", detail=f"mol_id={body.mol_id}")
        return MoleculeGetResponse(molecule=dict(row))


@router.post("/evidence")
async def mol_evidence(body: MoleculeEvidenceRequest) -> MoleculeEvidenceResponse:
    """Return the full evidence chain for a canonical molecule.

    Joins ``molecules`` for metadata; returns the molecule record plus
    the full ``evidence`` list (untruncated).
    """
    root, db = _get_db(body)
    canonical_smiles = body.canonical_smiles
    with db.mol_conn() as conn:
        mol_row = conn.execute(
            "SELECT * FROM molecules WHERE mol_id = ? OR canonical_smiles = ?",
            (canonical_smiles, canonical_smiles),
        ).fetchone()
        if not mol_row:
            raise NotFoundError(
                "molecule not found", detail=f"canonical_smiles={canonical_smiles}"
            )
        items = _attach_evidence_batch(conn, root, [dict(mol_row)], limit=_EVIDENCE_FULL_LIMIT)
        mol = items[0]
    return MoleculeEvidenceResponse(molecule=mol, evidence=mol.get("evidence", []))



@router.post("/create")
async def mol_create(body: MoleculeCreateRequest) -> MoleculeCreateResponse:
    root, db = _get_db(body)
    mol_id = body.mol_id or str(uuid.uuid4())
    with db.mol_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO molecules (mol_id, smiles, esmiles, name, source_type, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (mol_id, body.smiles, body.esmiles, body.name, body.source_type, "active"),
        )
    return MoleculeCreateResponse(mol_id=mol_id)


@router.put("/{mol_id}")
async def mol_update(mol_id: str, body: MoleculeUpdateRequest) -> MoleculeUpdateResponse:
    root, db = _get_db(body)
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
        raise ValidationError("no fields to update")
    params.append(mol_id)
    with db.mol_conn() as conn:
        conn.execute(f"UPDATE molecules SET {', '.join(fields)} WHERE mol_id = ?", params)
    return MoleculeUpdateResponse()


@router.delete("/{mol_id}")
async def mol_delete(mol_id: str, body: MoleculeDeleteRequest) -> MoleculeDeleteResponse:
    root, db = _get_db(body)
    with db.mol_conn() as conn:
        conn.execute("DELETE FROM molecules WHERE mol_id = ?", (mol_id,))
    return MoleculeDeleteResponse()


@router.post("/stats")
async def mol_stats(body: MoleculeStatsRequest) -> MoleculeStatsResponse:
    root, db = _get_db(body)
    with db.mol_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM molecules").fetchone()[0]
        by_status = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM molecules GROUP BY status"
        ).fetchall()
        by_source = conn.execute(
            "SELECT source_type, COUNT(*) as cnt FROM molecules GROUP BY source_type"
        ).fetchall()
    return MoleculeStatsResponse(
        total=total,
        by_status={r["status"]: r["cnt"] for r in by_status},
        by_source={r["source_type"]: r["cnt"] for r in by_source},
    )
