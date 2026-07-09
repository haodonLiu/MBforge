# DEPRECATED 2026-07-08: 将随前端 pdfService.ts 迁移完成后删除。
# 替代端点见 routers/detection_cache.py (cache-aware) 与 routers/moldet_api.py
# 改造后的新主链路 (FT detector + MolScribe)。此文件仅保留作为 fallback,
# 防止前端尚未迁移时出现 404。
"""Legacy /api/v1/models/* routes used by the stale frontend pdfService.

These endpoints live in the mounted model server (see mbforge.server) and are
included with an empty prefix so that the external path stays exactly what the
frontend expects: /api/v1/models/extract/...

New code should prefer the modern /api/v1/detection-cache/* endpoints.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..core.database import DatabaseManager
from ..utils.helpers import ValidationError
from ..utils.logger import get_logger

logger = get_logger("mbforge.legacy_models")

router = APIRouter()


def _load_cached_detections(
    project_root: str, doc_id: str, page: int
) -> dict[str, Any]:
    """Read molecule_detections rows and map them to ExtractionResult-shaped dicts."""
    db = DatabaseManager.get(project_root)
    rows = []
    try:
        with db.mol_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM molecule_detections WHERE doc_id = ? AND page = ?",
                (doc_id, page),
            ).fetchall()
    except Exception:
        # Database may not exist yet for a fresh project; treat as empty cache.
        rows = []

    results: list[dict[str, Any]] = []
    for row in rows:
        moldet_conf = row["conf_moldet"] or 0.0
        scribe_conf = row["conf_molscribe"] or 0.0
        composite_conf = moldet_conf * scribe_conf if scribe_conf > 0 else moldet_conf
        results.append(
            {
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
            }
        )

    return {
        "results": results,
        "count": len(results),
        "source": "cache" if results else "cache_miss",
    }


@router.post("/extract/cached-detections")
async def extract_cached_detections(body: dict) -> dict[str, Any]:
    """Return cached detections for a single page without running inference."""
    project_root = body.get("project_root", "")
    doc_id = body.get("doc_id", "")
    page = body.get("page", 0)
    if not project_root or not doc_id:
        raise ValidationError("project_root and doc_id are required")
    return _load_cached_detections(project_root, doc_id, page)


@router.post("/extract/cached-page")
async def extract_cached_page(body: dict) -> dict[str, Any]:
    """Cache-aware page extraction: DEPRECATED 2026-07-08.

    The legacy MolDet pipeline (Doc + General detectors, RapidOCR coref)
    has been replaced by the joint MolDetv2-FT detector. This endpoint is
    kept as a stub so old frontends do not 404 during the migration window.
    Frontend pdfService.ts still calls this; once that is updated to use
    the modern /api/v1/moldet/extract-pdf-page endpoint, this file can be
    removed.
    """
    return {
        "success": False,
        "error": (
            "DEPRECATED 2026-07-08. The legacy MolDet pipeline has been "
            "replaced by the joint MolDetv2-FT detector. Use "
            "POST /api/v1/moldet/extract-pdf-page (FT + MolScribe, full PDF "
            "pipeline) instead. See docs/2026-07-08-ft-migration.md."
        ),
        "status_code": 503,
        "results": [],
        "count": 0,
        "source": "deprecated",
    }


@router.post("/extract/clear-cache-doc")
async def extract_clear_cache_doc(body: dict) -> dict[str, Any]:
    """Clear detection cache for a single document."""
    project_root = body.get("project_root", "")
    doc_id = body.get("doc_id", "")
    if not project_root or not doc_id:
        raise ValidationError("project_root and doc_id are required")

    try:
        db = DatabaseManager.get(project_root)
        with db.mol_conn() as conn:
            conn.execute("DELETE FROM molecule_detections WHERE doc_id = ?", (doc_id,))
            conn.commit()
        return {"success": True, "cleared": 0}
    except Exception as e:
        logger.warning("Failed to clear detection cache: %s", e)
        return {"success": True, "cleared": 0}


@router.post("/extract/cache-stats")
async def extract_cache_stats(body: dict) -> dict[str, Any]:
    """Return detection cache stats."""
    project_root = body.get("project_root", "")
    if not project_root:
        raise ValidationError("project_root is required")

    try:
        db = DatabaseManager.get(project_root)
        with db.mol_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS page_count, COUNT(DISTINCT doc_id) AS doc_count FROM molecule_detections"
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
