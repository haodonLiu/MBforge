"""Detection cache endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.post("/get")
async def detection_get(body: dict) -> dict:
    root = body.get("project_root", "")
    doc_id = body.get("doc_id", "")
    page = body.get("page", 0)
    if not root or not doc_id:
        return {"success": False, "detections": []}
    from ..core.database import DatabaseManager

    db = DatabaseManager(root)
    with db.mol_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM molecule_detections WHERE doc_id = ? AND page = ?",
            (doc_id, page),
        ).fetchall()
    return {"success": True, "detections": [dict(r) for r in rows]}


@router.post("/save")
async def detection_save(body: dict) -> dict:
    root = body.get("project_root", "")
    detections = body.get("detections", [])
    if not root or not detections:
        return {"success": False, "error": "project_root and detections required"}
    from ..core.database import DatabaseManager

    db = DatabaseManager(root)
    with db.mol_conn() as conn:
        for det in detections:
            conn.execute(
                "INSERT OR REPLACE INTO molecule_detections "
                "(mol_id, doc_id, page, bbox_x0, bbox_y0, bbox_x1, bbox_y1, crop_relpath, conf_moldet, conf_molscribe) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    det.get("mol_id"), det.get("doc_id"), det.get("page"),
                    det.get("bbox_x0"), det.get("bbox_y0"), det.get("bbox_x1"), det.get("bbox_y1"),
                    det.get("crop_relpath"), det.get("conf_moldet"), det.get("conf_molscribe"),
                ),
            )
    return {"success": True}
