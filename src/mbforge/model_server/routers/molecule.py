"""分子数据库路由 (Browser dev fallback).

这些端点仅在前端以纯浏览器模式运行时作为降级使用。
分子列表/搜索/统计的主路径已在 Rust (Tauri) 中实现。
"""

from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Depends

from ...core.mol_database import MoleculeDatabase
from ...core.project import Project
from ...utils.logger import get_logger
from ..dependencies import get_project_from_root

logger = get_logger(__name__)
router = APIRouter()


@router.get("/list")
async def list_molecules(
    project_root: str,
    limit: int = 100,
    offset: int = 0,
    project: Project = Depends(get_project_from_root),
) -> dict[str, Any]:
    try:
        db = MoleculeDatabase(project.root)
        results = db.list_all(limit=limit, offset=offset)
        return {"success": True, "molecules": [r.to_dict() for r in results]}
    except Exception as e:
        logger.error(f"List molecules failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/stats")
async def molecule_stats(
    project_root: str,
    project: Project = Depends(get_project_from_root),
) -> dict[str, Any]:
    try:
        db = MoleculeDatabase(project.root)
        stats = db.get_stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        logger.error(f"Molecule stats failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/search")
async def search_molecules(
    project_root: str,
    q: str = "",
    limit: int = 20,
    project: Project = Depends(get_project_from_root),
) -> dict[str, Any]:
    try:
        db = MoleculeDatabase(project.root)
        conn = db._conn
        if conn is None:
            return {"success": False, "error": "Database not initialized"}
        rows = conn.execute(
            "SELECT * FROM molecules WHERE name LIKE ? OR esmiles LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{q}%", f"%{q}%", limit),
        ).fetchall()
        results = [db._row_to_record(r).to_dict() for r in rows]
        return {"success": True, "molecules": results}
    except Exception as e:
        logger.error(f"Search molecules failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
