"""Persist normalized molecule candidates to the database.

For each candidate (a single canonical SMILES, possibly with multiple
detections), the persist step:

1. Upserts a `molecules` row keyed by `canonical_smiles` so the same
   molecule observed in different documents collapses to a single record.
2. Inserts one `molecule_detections` row per primary detection (legacy table
   still maintained for back-compat readers).
3. Inserts one first-class `evidence` row (kind='figure') per primary
   detection. The evidence table is the new aggregate store and is the
   primary surface the molecule router reads.
"""

from __future__ import annotations

import sqlite3
from contextlib import nullcontext
from typing import Any

from ..core.database import DatabaseManager
from ..utils.logger import get_logger
from .normalize import NormalizedMolecule

logger = get_logger(__name__)


def persist_molecule_candidates(
    library_root: str,
    doc_id: str,
    candidates: list[NormalizedMolecule],
    conn: sqlite3.Connection | None = None,
    activity_records: list[Any] | None = None,
) -> None:
    """Upsert canonical molecule rows + insert detection / evidence rows.

    Args:
        library_root: Project root directory.
        doc_id: Source document ID.
        candidates: Normalized molecule candidates produced by
            :mod:`mbforge.pipeline.normalize`.
        conn: Optional open molecules DB connection. When provided, writes are
            performed on this connection and the caller is responsible for
            commit/rollback (used by the pipeline transaction wrapper).
    """
    db = DatabaseManager.get(library_root)
    db.initialize()

    conn_manager = nullcontext(conn) if conn is not None else db.mol_conn()
    persisted = 0
    with conn_manager as active_conn:
        if active_conn is None:
            raise RuntimeError("No database connection available")
        # Phase 0 activity persistence: build a page → list-of-records index
        # so each candidate can look up the best activity on the same page.
        # When no ``page_num`` is set on the activity records (e.g. the LLM
        # reorganize stripped ``<!-- PAGE N -->`` markers) this index stays
        # empty and the activity write inside the candidate loop becomes a
        # no-op. The plan's Phase 1 follow-up will switch to row alignment.
        page_to_activities: dict[int, list[Any]] = {}
        if activity_records:
            for rec in activity_records:
                if getattr(rec, "page_num", None) is None:
                    continue
                page_to_activities.setdefault(rec.page_num, []).append(rec)
            for recs in page_to_activities.values():
                recs.sort(key=lambda r: r.confidence, reverse=True)
        used_pages: set[int] = set()  # noqa: F841 — reserved for Phase 1
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

            # 1. Upsert molecules row keyed by canonical_smiles (canonical
            #    aggregate). The mol_id IS the canonical_smiles.
            canonical_smiles = c.canonical_smiles or c.esmiles
            if not canonical_smiles:
                logger.warning(
                    "Skipping candidate with no canonical_smiles for %s",
                    doc_id,
                )
                continue
            active_conn.execute(
                """
                INSERT INTO molecules
                    (mol_id, smiles, esmiles, name, source_type, status,
                     canonical_smiles)
                VALUES (?, ?, ?, ?, 'image', 'pending', ?)
                ON CONFLICT(mol_id) DO UPDATE SET
                    canonical_smiles = COALESCE(molecules.canonical_smiles, excluded.canonical_smiles)
                """,
                (
                    canonical_smiles,
                    canonical_smiles,
                    c.esmiles,
                    c.name or "",
                    canonical_smiles,
                ),
            )
            # 2. Insert molecule_detections row (mol_id now non-null).
            active_conn.execute(
                """
                INSERT INTO molecule_detections (
                    mol_id, doc_id, page, bbox_x0, bbox_y0, bbox_x1, bbox_y1,
                    crop_relpath, conf_moldet, conf_molscribe,
                    vlm_verified_esmiles
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    canonical_smiles,
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
            # 3. Insert first-class evidence row (figure kind).
            active_conn.execute(
                """
                INSERT INTO evidence
                    (canonical_smiles, mol_id, doc_id, page,
                     bbox_x0, bbox_y0, bbox_x1, bbox_y1,
                     crop_relpath, role, kind, confidence, source_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'detected', 'figure', ?, 'image')
                """,
                (
                    canonical_smiles,
                    canonical_smiles,
                    doc_id,
                    primary.page,
                    bbox[0] if bbox else None,
                    bbox[1] if bbox else None,
                    bbox[2] if bbox else None,
                    bbox[3] if bbox else None,
                    primary.image_path,
                    conf_moldet,
                ),
            )

            # 4. Phase 0 activity write — page-proximity linking. Update
            #    the molecules row's activity columns and insert a
            #    ``kind='table'`` evidence row when a best-confidence
            #    activity exists on the same page as the candidate's
            #    primary detection. ``used_pages`` is consulted to avoid
            #    assigning the same activity to multiple molecules on the
            #    same page (Phase 1 will tighten this with row alignment).
            if (
                activity_records
                and primary.page is not None
                and primary.page in page_to_activities
                and primary.page not in used_pages
            ):
                rec = page_to_activities[primary.page][0]
                active_conn.execute(
                    """
                    UPDATE molecules
                    SET activity = ?,
                        activity_type = ?,
                        units = ?
                    WHERE mol_id = ?
                    """,
                    (rec.value, rec.activity_type, rec.unit, canonical_smiles),
                )
                active_conn.execute(
                    """
                    INSERT INTO evidence
                        (canonical_smiles, mol_id, doc_id, page,
                         context_text, role, kind, confidence, source_type)
                    VALUES (?, ?, ?, ?, ?, 'activity_data', 'table', ?, 'llm_extraction')
                    """,
                    (
                        canonical_smiles,
                        canonical_smiles,
                        doc_id,
                        rec.page_num,
                        (rec.raw_text or "")[:500],
                        rec.confidence,
                    ),
                )
                used_pages.add(primary.page)
            persisted += 1

    logger.info(
        "Persisted %d molecule candidates for %s",
        persisted,
        doc_id,
    )
