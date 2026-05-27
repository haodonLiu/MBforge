"""分子数据库路由."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...core.mol_database import MoleculeDatabase, MoleculeRecord
from ...core.project import Project
from ...utils.logger import get_logger
from ..dependencies import get_project_from_root

logger = get_logger(__name__)
router = APIRouter()


class MoleculeAddRequest(BaseModel):
    project_root: str
    smiles: str
    name: str = ""
    source_doc: str = ""
    activity: float | None = None
    activity_type: str = ""
    units: str = "nM"


@router.get("/list")
async def list_molecules(
    project_root: str,
    limit: int = 100,
    offset: int = 0,
    project: Project = Depends(get_project_from_root),
) -> dict:
    try:
        db = MoleculeDatabase(project.root)
        results = db.list_all(limit=limit, offset=offset)
        return {"success": True, "molecules": results}
    except Exception as e:
        logger.error(f"List molecules failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/stats")
async def molecule_stats(
    project_root: str,
    project: Project = Depends(get_project_from_root),
) -> dict:
    try:
        db = MoleculeDatabase(project.root)
        stats = db.get_stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        logger.error(f"Molecule stats failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/add")
async def add_molecule(
    req: MoleculeAddRequest,
    project: Project = Depends(get_project_from_root),
) -> dict:
    try:
        db = MoleculeDatabase(project.root)
        record = MoleculeRecord(
            smiles=req.smiles,
            name=req.name,
            source_doc=req.source_doc,
            activity=req.activity,
            activity_type=req.activity_type,
            units=req.units,
        )
        db.add_molecule(record)
        return {"success": True, "mol_id": record.mol_id}
    except Exception as e:
        logger.error(f"Add molecule failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/search")
async def search_molecules(
    project_root: str,
    q: str = "",
    limit: int = 20,
    project: Project = Depends(get_project_from_root),
) -> dict:
    try:
        db = MoleculeDatabase(project.root)
        conn = db._conn
        if conn is None:
            return {"success": False, "error": "Database not initialized"}
        rows = conn.execute(
            "SELECT * FROM molecules WHERE name LIKE ? OR smiles LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{q}%", f"%{q}%", limit),
        ).fetchall()
        results = [db._row_to_record(r) for r in rows]
        return {"success": True, "molecules": results}
    except Exception as e:
        logger.error(f"Search molecules failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
