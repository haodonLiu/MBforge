"""Detection cache endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from ._path_utils import resolve_library_root, validate_doc_id

router = APIRouter()


@router.post("/get")
async def detection_get(body: dict) -> dict:
    root = body.get("library_root", "")
    doc_id = body.get("doc_id", "")
    page = body.get("page", 0)
    if not root or not doc_id:
        return {"success": False, "detections": []}

    # Reject traversal in both the library root and the document id.
    root_path = resolve_library_root(root)
    validate_doc_id(doc_id)

    from ..core.database import DatabaseManager

    db = DatabaseManager.get(str(root_path))
    with db.mol_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM molecule_detections WHERE doc_id = ? AND page = ?",
            (doc_id, page),
        ).fetchall()
    return {"success": True, "detections": [dict(r) for r in rows]}


@router.post("/save")
async def detection_save(body: dict) -> dict:
    root = body.get("library_root", "")
    detections = body.get("detections", [])
    if not root or not detections:
        return {"success": False, "error": "library_root and detections required"}

    root_path = resolve_library_root(root)
    for det in detections:
        validate_doc_id(det.get("doc_id", ""))

    from ..core.database import DatabaseManager

    db = DatabaseManager.get(str(root_path))
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


@router.post("/extract-page")
async def detection_extract_page(body: dict) -> dict:
    """Cache-aware single-page molecule detection stub."""
    return {"results": [], "count": 0, "source": "cache_miss"}


@router.post("/stats")
async def detection_stats(body: dict) -> dict:
    """Detection cache stats stub."""
    return {"disk_usage_bytes": 0, "cached_page_count": 0, "cached_doc_count": 0, "schema_version": 1}


@router.post("/clear")
async def detection_clear(body: dict) -> dict:
    """Clear all detection cache stub."""
    return {"success": True, "cleared": 0}


@router.post("/clear-doc")
async def detection_clear_doc(body: dict) -> dict:
    """Clear detection cache for a specific document stub."""
    return {"success": True, "cleared": 0}


@router.post("/batch-scan")
async def detection_batch_scan(body: dict) -> dict:
    """Batch quick MoldDet scan stub."""
    return {"results": [], "processed": 0, "total": 0, "errors": []}
