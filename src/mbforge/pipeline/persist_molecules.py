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
        # no-op.
        page_to_activities: dict[int, list[Any]] = {}
        if activity_records:
            for rec in activity_records:
                if getattr(rec, "page_num", None) is None:
                    continue
                page_to_activities.setdefault(rec.page_num, []).append(rec)
            for recs in page_to_activities.values():
                recs.sort(key=lambda r: r.confidence, reverse=True)
        used_pages: set[int] = set()
        # Phase 1: track (table_idx, row_idx) pairs to prevent double assignment.
        used_rows: set[tuple[int, int]] = set()
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

            # 4. Phase 1 activity write — row alignment first, then page fallback.
            #    Try to match by row_label→mol.name or row_smiles→canonical_smiles.
            #    On success write evidence(kind='table_row') with table coordinates.
            #    On failure degrade to Phase 0 page-proximity (kind='table').
            active_rec, align_kind = (None, None)
            if activity_records:
                active_rec, align_kind = _link_activity_to_molecule(
                    c, activity_records, used_rows
                )

            if active_rec is not None and align_kind == "table_row":
                # Row-alignment match — write kind='table_row' evidence with
                # table_idx / row_idx / col_idx for front-end table-cell lookup.
                active_conn.execute(
                    """
                    UPDATE molecules
                    SET activity = ?,
                        activity_type = ?,
                        units = ?
                    WHERE mol_id = ?
                    """,
                    (
                        active_rec.value,
                        active_rec.activity_type,
                        active_rec.unit,
                        canonical_smiles,
                    ),
                )
                active_conn.execute(
                    """
                    INSERT INTO evidence
                        (canonical_smiles, mol_id, doc_id, page,
                         context_text, role, kind, confidence, source_type,
                         row_label, table_idx, row_idx, col_idx)
                    VALUES (?, ?, ?, ?, ?, 'activity_data', 'table_row', ?, 'llm_extraction',
                            ?, ?, ?, ?)
                    """,
                    (
                        canonical_smiles,
                        canonical_smiles,
                        doc_id,
                        getattr(active_rec, "page_num", None),
                        (getattr(active_rec, "raw_text", "") or "")[:500],
                        active_rec.confidence,
                        getattr(active_rec, "row_label", None),
                        getattr(active_rec, "table_idx", None),
                        getattr(active_rec, "row_idx", None),
                        getattr(active_rec, "col_idx", None),
                    ),
                )
            elif (
                activity_records
                and primary.page is not None
                and primary.page in page_to_activities
                and primary.page not in used_pages
            ):
                # Phase 0 fallback: page-proximity, write kind='table'.
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


def _link_activity_to_molecule(
    candidate: Any,
    activity_records: list[Any],
    used_rows: set[tuple[int, int]],  # (table_idx, row_idx)
) -> tuple[Any, str | None]:
    """Return (best_matching_activity, alignment_kind) or (None, None).

    Tries in order:
    1. Row alignment by ``row_label == mol.name`` (exact, stripped).
    2. Row alignment by ``row_smiles == mol.canonical_smiles`` or
       ``row_smiles == mol.esmiles``.
    3. No match → caller falls back to page-proximity.

    ``alignment_kind`` is ``'table_row'`` when a row match is found,
    ``None`` otherwise.
    """
    mol_name = (getattr(candidate, "name", "") or "").strip()
    mol_canonical = getattr(candidate, "canonical_smiles", "") or ""
    mol_esmiles = getattr(candidate, "esmiles", "") or ""

    for rec in activity_records:
        table_idx = getattr(rec, "table_idx", None)
        row_idx = getattr(rec, "row_idx", None)
        row_label = getattr(rec, "row_label", None)
        row_smiles = getattr(rec, "row_smiles", None)

        # Step 1: match by row_label == mol.name
        if row_label and mol_name and row_label.strip().lower() == mol_name.lower():
            if table_idx is not None and row_idx is not None:
                key = (table_idx, row_idx)
                if key not in used_rows:
                    used_rows.add(key)
                    return rec, "table_row"
            else:
                # No table/row coordinates — can't check used_rows, but still match
                return rec, "table_row"

        # Step 2: match by row_smiles == canonical_smiles or esmiles
        if row_smiles and (
            (mol_canonical and row_smiles.strip() == mol_canonical.strip())
            or (mol_esmiles and row_smiles.strip() == mol_esmiles.strip())
        ):
            if table_idx is not None and row_idx is not None:
                key = (table_idx, row_idx)
                if key not in used_rows:
                    used_rows.add(key)
                    return rec, "table_row"
            else:
                return rec, "table_row"

    return None, None
