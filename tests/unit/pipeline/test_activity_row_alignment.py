"""Phase 1 row-alignment tests for _link_activity_to_molecule and persistence.

Covers the three-tier matching strategy:
1. row_label → mol.name match → kind='table_row'
2. row_smiles → canonical_smiles/esmiles match → kind='table_row'
3. No match at all → kind='table' (Phase 0 page-proximity fallback)
4. Double-assignment prevention via (table_idx, row_idx) set
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from mbforge.core.database import DatabaseManager
from mbforge.pipeline.extract_activities import ActivityRecord
from mbforge.pipeline.persist_molecules import (
    _link_activity_to_molecule,
    persist_molecule_candidates,
)


def _fake_candidate(name: str = "", smiles: str = "CCO") -> MagicMock:
    cand = MagicMock()
    cand.status = "pending"
    cand.canonical_smiles = smiles
    cand.esmiles = smiles
    cand.name = name
    cand.sources = ["image"]
    cand.detections = [
        MagicMock(bbox=(0, 0, 1, 1), page=1, image_path="/tmp/c.png", confidence=0.9)
    ]
    return cand


def _row_record(
    row_label: str | None = "1a",
    row_smiles: str | None = None,
    table_idx: int = 0,
    row_idx: int = 1,
    col_idx: int = 1,
    page_num: int = 1,
) -> ActivityRecord:
    return ActivityRecord(
        activity_type="IC50",
        value=12.5,
        value_original=12.5,
        unit="nM",
        operator="=",
        target="EGFR",
        assay_type="enzymatic",
        raw_text="| 1a | 12.5 |",
        confidence=0.9,
        page_num=page_num,
        evidence_kind="table",
        evidence_bbox=None,
        table_idx=table_idx,
        row_idx=row_idx,
        col_idx=col_idx,
        row_label=row_label,
        row_smiles=row_smiles,
    )


def test_row_alignment_matches_by_name() -> None:
    """A candidate with name '1a' matches an activity with row_label '1a'."""
    candidate = _fake_candidate(name="1a")
    activity = _row_record(row_label="1a")
    used_rows: set[tuple[int, int]] = set()

    rec, kind = _link_activity_to_molecule(candidate, [activity], used_rows)
    assert rec is not None
    assert kind == "table_row"
    assert (0, 1) in used_rows  # (table_idx, row_idx) recorded


def test_row_alignment_matches_by_name_case_insensitive() -> None:
    """Name matching is case-insensitive and strip-normalized."""
    candidate = _fake_candidate(name=" 1A ")
    activity = _row_record(row_label="1a")
    used_rows: set[tuple[int, int]] = set()

    rec, kind = _link_activity_to_molecule(candidate, [activity], used_rows)
    assert rec is not None
    assert kind == "table_row"


def test_row_alignment_falls_back_to_smiles() -> None:
    """When name doesn't match but row_smiles matches esmiles → table_row."""
    candidate = _fake_candidate(name="Compound Z", smiles="C1=CC=CC=C1")
    activity = _row_record(row_label="not_matching", row_smiles="C1=CC=CC=C1")
    used_rows: set[tuple[int, int]] = set()

    rec, kind = _link_activity_to_molecule(candidate, [activity], used_rows)
    assert rec is not None
    assert kind == "table_row"


def test_row_alignment_no_match_falls_to_none() -> None:
    """When neither name nor SMILES match, returns (None, None)."""
    candidate = _fake_candidate(name="X42", smiles="CCC")
    activity = _row_record(row_label="Y99", row_smiles="C1=CC=CC=C1")
    used_rows: set[tuple[int, int]] = set()

    rec, kind = _link_activity_to_molecule(candidate, [activity], used_rows)
    assert rec is None
    assert kind is None


def test_row_alignment_no_double_assignment(tmp_path: Path) -> None:
    """A (table_idx, row_idx) pair is only assigned once.

    Two candidates both matching row_label '1a' — only the first gets the
    activity; the second falls back to page-proximity (kind='table')."""
    library_root = tmp_path / "library"
    library_root.mkdir(parents=True, exist_ok=True)

    c1 = _fake_candidate(name="1a", smiles="CCO")
    c2 = _fake_candidate(name="1a", smiles="CCN")
    activity = _row_record(row_label="1a", table_idx=0, row_idx=1)

    persist_molecule_candidates(
        str(library_root),
        doc_id="doc-double",
        candidates=[c1, c2],  # type: ignore[arg-type]
        activity_records=[activity],
    )

    db = DatabaseManager.get(str(library_root))
    with db.mol_conn() as conn:
        rows = conn.execute(
            "SELECT mol_id, kind FROM evidence WHERE kind IN ('table_row', 'table')"
        ).fetchall()
    # First candidate (CCO) gets table_row, second (CCN) gets table
    kinds = {r["mol_id"]: r["kind"] for r in rows}
    assert kinds.get("CCO") == "table_row"
    assert kinds.get("CCN") == "table"
