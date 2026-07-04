"""Persist normalized molecule candidates to the database."""

from __future__ import annotations

from ..core.database import DatabaseManager
from ..utils.logger import get_logger
from .normalize import NormalizedMolecule

logger = get_logger(__name__)


def persist_molecule_candidates(
    project_root: str,
    doc_id: str,
    candidates: list[NormalizedMolecule],
) -> None:
    """Write pending molecule candidates to molecule_detections table.

    Args:
        project_root: Project root directory.
        doc_id: Source document ID.
        candidates: Normalized molecule candidates.
    """
    db = DatabaseManager.get(project_root)
    db.initialize()

    persisted = 0
    with db.mol_conn() as conn:
        for c in candidates:
            if c.status == "rejected":
                continue

            if not c.detections:
                logger.warning(
                    "Skipping candidate with no detections for %s (%s)",
                    doc_id,
                    c.esmiles,
                )
                continue

            primary = c.detections[0]
            bbox = primary.bbox
            conf_moldet = primary.confidence

            conn.execute(
                """
                INSERT INTO molecule_detections (
                    doc_id, page, bbox_x0, bbox_y0, bbox_x1, bbox_y1,
                    crop_relpath, conf_moldet, conf_molscribe,
                    vlm_verified_esmiles
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    primary.page,
                    bbox[0] if bbox else None,
                    bbox[1] if bbox else None,
                    bbox[2] if bbox else None,
                    bbox[3] if bbox else None,
                    primary.image_path,
                    conf_moldet,
                    None,
                    c.esmiles,
                ),
            )
            persisted += 1

    logger.info(
        "Persisted %d molecule candidates for %s",
        persisted,
        doc_id,
    )
