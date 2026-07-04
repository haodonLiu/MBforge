"""Persist normalized molecule candidates to the database."""

from __future__ import annotations

from ..core.database import DatabaseManager
from ..utils.logger import get_logger
from .normalize import NormalizedMolecule

logger = get_logger("mbforge.pipeline.persist_molecules")


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

    with db.mol_conn() as conn:
        for c in candidates:
            if c.status == "rejected":
                continue

            primary = c.detections[0] if c.detections else None
            bbox = primary.bbox if primary else None
            conf_moldet = primary.confidence if primary else 0.0

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
                    primary.page if primary else None,
                    bbox[0] if bbox else None,
                    bbox[1] if bbox else None,
                    bbox[2] if bbox else None,
                    bbox[3] if bbox else None,
                    primary.image_path if primary else None,
                    conf_moldet,
                    0.0,
                    c.canonical_smiles,
                ),
            )

    logger.info(
        "Persisted %d molecule candidates for %s",
        len([c for c in candidates if c.status != "rejected"]),
        doc_id,
    )
