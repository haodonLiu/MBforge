"""Detection cache endpoints — molecule_detections table under library DB.

Canonical FE surface for read / clear / stats. Logic ported from
``legacy_models.py`` (2026-07-14) so ``/api/v1/models/extract/*`` can retire
once FE leaves those paths.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..core.database import DatabaseManager
from ..utils.helpers import ValidationError
from ..utils.logger import get_logger
from ._path_utils import resolve_library_root, validate_doc_id

logger = get_logger("mbforge.detection_cache")

router = APIRouter()


def _row_to_result(row: Any) -> dict[str, Any]:
    """Map molecule_detections row → ExtractionResult-shaped dict."""
    moldet_conf = row["conf_moldet"] or 0.0
    scribe_conf = row["conf_molscribe"] or 0.0
    composite_conf = moldet_conf * scribe_conf if scribe_conf > 0 else moldet_conf
    return {
        "esmiles": row["vlm_verified_esmiles"] or "",
        "name": row["mol_id"] or "",
        "source": "image",
        "moldet_conf": moldet_conf,
        "scribe_conf": scribe_conf,
        "composite_conf": composite_conf,
        "bbox_pdf": [
            row["bbox_x0"] or 0.0,
            row["bbox_y0"] or 0.0,
            row["bbox_x1"] or 0.0,
            row["bbox_y1"] or 0.0,
        ],
        "page_idx": row["page"],
        "context_text": "",
        "mol_img_path": row["crop_relpath"],
        "status": "pending",
        "properties": {},
        # keep raw fields for callers that still expect SQL shape
        "mol_id": row["mol_id"],
        "doc_id": row["doc_id"],
        "page": row["page"],
        "bbox_x0": row["bbox_x0"],
        "bbox_y0": row["bbox_y0"],
        "bbox_x1": row["bbox_x1"],
        "bbox_y1": row["bbox_y1"],
        "crop_relpath": row["crop_relpath"],
        "conf_moldet": row["conf_moldet"],
        "conf_molscribe": row["conf_molscribe"],
    }


def _load_cached_detections(
    library_root: str, doc_id: str, page: int
) -> dict[str, Any]:
    db = DatabaseManager.get(library_root)
    db.initialize()
    rows: list[Any] = []
    try:
        with db.mol_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM molecule_detections WHERE doc_id = ? AND page = ?",
                (doc_id, page),
            ).fetchall()
    except Exception as e:  # noqa: BLE001 - fresh library may lack table yet
        logger.debug("load detections failed: %s", e)
        rows = []

    results = [_row_to_result(r) for r in rows]
    return {
        "success": True,
        "results": results,
        "detections": results,  # back-compat alias
        "count": len(results),
        "source": "cache" if results else "cache_miss",
    }


@router.post("/get")
async def detection_get(body: dict) -> dict:
    root = body.get("library_root", "") or body.get("libraryRoot", "")
    doc_id = body.get("doc_id", "") or body.get("docId", "")
    page = body.get("page", 0)
    if not root or not doc_id:
        return {
            "success": False,
            "results": [],
            "detections": [],
            "count": 0,
            "source": "cache_miss",
        }

    root_path = resolve_library_root(root)
    validate_doc_id(doc_id)
    return _load_cached_detections(str(root_path), doc_id, int(page))


@router.post("/save")
async def detection_save(body: dict) -> dict:
    root = body.get("library_root", "") or body.get("libraryRoot", "")
    detections = body.get("detections", [])
    if not root or not detections:
        return {"success": False, "error": "library_root and detections required"}

    root_path = resolve_library_root(root)
    for det in detections:
        validate_doc_id(det.get("doc_id", ""))

    db = DatabaseManager.get(str(root_path))
    db.initialize()
    with db.mol_conn() as conn:
        for det in detections:
            conn.execute(
                "INSERT OR REPLACE INTO molecule_detections "
                "(mol_id, doc_id, page, bbox_x0, bbox_y0, bbox_x1, bbox_y1, "
                "crop_relpath, conf_moldet, conf_molscribe) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    det.get("mol_id"),
                    det.get("doc_id"),
                    det.get("page"),
                    det.get("bbox_x0"),
                    det.get("bbox_y0"),
                    det.get("bbox_x1"),
                    det.get("bbox_y1"),
                    det.get("crop_relpath"),
                    det.get("conf_moldet"),
                    det.get("conf_molscribe"),
                ),
            )
    return {"success": True}


@router.post("/extract-page")
async def detection_extract_page(body: dict) -> dict:
    """Cache-aware single-page read (no inference).

    Live detect remains ``POST /api/v1/moldet/extract-pdf``. This endpoint only
    returns rows already in ``molecule_detections``.
    """
    root = body.get("library_root", "") or body.get("libraryRoot", "")
    doc_id = body.get("doc_id", "") or body.get("docId", "")
    page = body.get("page", 0)
    if not root or not doc_id:
        raise ValidationError("library_root and doc_id are required")
    root_path = resolve_library_root(root)
    validate_doc_id(doc_id)
    return _load_cached_detections(str(root_path), doc_id, int(page))


@router.post("/stats")
async def detection_stats(body: dict) -> dict:
    root = body.get("library_root", "") or body.get("libraryRoot", "")
    if not root:
        raise ValidationError("library_root is required")

    root_path = resolve_library_root(root)
    try:
        db = DatabaseManager.get(str(root_path))
        db.initialize()
        with db.mol_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS page_count, "
                "COUNT(DISTINCT doc_id) AS doc_count "
                "FROM molecule_detections"
            ).fetchone()
        return {
            "disk_usage_bytes": 0,
            "cached_page_count": row["page_count"] if row else 0,
            "cached_doc_count": row["doc_count"] if row else 0,
            "schema_version": 1,
        }
    except Exception as e:
        logger.warning("Failed to read detection cache stats: %s", e)
        return {
            "disk_usage_bytes": 0,
            "cached_page_count": 0,
            "cached_doc_count": 0,
            "schema_version": 1,
        }


@router.post("/clear")
async def detection_clear(body: dict) -> dict:
    root = body.get("library_root", "") or body.get("libraryRoot", "")
    if not root:
        raise ValidationError("library_root is required")

    root_path = resolve_library_root(root)
    try:
        db = DatabaseManager.get(str(root_path))
        db.initialize()
        with db.mol_conn() as conn:
            cur = conn.execute("DELETE FROM molecule_detections")
            cleared = cur.rowcount
        return {"success": True, "cleared": cleared}
    except Exception as e:
        logger.warning("Failed to clear detection cache: %s", e)
        return {"success": True, "cleared": 0}


@router.post("/clear-doc")
async def detection_clear_doc(body: dict) -> dict:
    root = body.get("library_root", "") or body.get("libraryRoot", "")
    doc_id = body.get("doc_id", "") or body.get("docId", "")
    if not root or not doc_id:
        raise ValidationError("library_root and doc_id are required")

    root_path = resolve_library_root(root)
    validate_doc_id(doc_id)
    try:
        db = DatabaseManager.get(str(root_path))
        db.initialize()
        with db.mol_conn() as conn:
            cur = conn.execute(
                "DELETE FROM molecule_detections WHERE doc_id = ?",
                (doc_id,),
            )
            cleared = cur.rowcount
        return {"success": True, "cleared": cleared}
    except Exception as e:
        logger.warning("Failed to clear detection cache for doc: %s", e)
        return {"success": True, "cleared": 0}


@router.post("/batch-scan")
async def detection_batch_scan(body: dict) -> dict:
    """Batch quick MoldDet scan — not implemented; fail closed."""
    return {
        "success": False,
        "error": "batch-scan not implemented; use /api/v1/moldet/extract-pdf per page",
        "results": [],
        "processed": 0,
        "total": 0,
        "errors": ["not_implemented"],
    }
