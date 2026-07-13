"""Unit tests for activity extraction and persistence wiring.

Covers:

1. `extract_activities_from_document` returns [] for a document with no
   markdown tables (no-op).
2. `persist_molecule_candidates` with activity_records on the same page
   writes activity columns + a kind='table' evidence row.
3. Page-mismatch between molecule and activity => no activity is written.
4. Back-compat: omitting activity_records leaves existing behavior unchanged.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mbforge.core.database import DatabaseManager
from mbforge.pipeline.extract_activities import (
    ActivityRecord,
    extract_activities_from_document,
    extract_activities_from_document_async,
)
from mbforge.pipeline.persist_molecules import persist_molecule_candidates


def _fake_candidate(page: int = 1) -> MagicMock:
    cand = MagicMock()
    cand.status = "pending"
    cand.canonical_smiles = "CCO"
    cand.esmiles = "CCO"
    cand.name = ""
    cand.sources = ["image"]
    cand.detections = [
        MagicMock(bbox=(0, 0, 1, 1), page=page, image_path="/tmp/c.png", confidence=0.9)
    ]
    return cand


def _make_activity_record(page_num: int = 1) -> ActivityRecord:
    return ActivityRecord(
        activity_type="IC50",
        value=12.5,
        value_original=12.5,
        unit="nM",
        operator="=",
        target="EGFR",
        assay_type="enzymatic",
        raw_text="| 1 | 12.5 |",
        confidence=0.9,
        page_num=page_num,
        evidence_kind="table",
        evidence_bbox=None,
    )


def test_extract_activities_no_tables_noop(tmp_path: Path) -> None:
    """extract_activities_from_document returns [] for markdown with no tables."""
    md_path = tmp_path / "no_tables.md"
    md_path.write_text(
        "<!-- PAGE 1 -->\nSome prose text. No tables here. Just words.\n",
        encoding="utf-8",
    )
    records = extract_activities_from_document(str(md_path), doc_id="doc-x")
    assert records == []


def test_persist_molecule_candidates_writes_activity_proximity(tmp_path: Path) -> None:
    """Direct call to persist_molecule_candidates with activity_records writes
    the activity columns when the candidate is on the same page as a record."""
    library_root = tmp_path / "library"
    library_root.mkdir(parents=True, exist_ok=True)

    candidate = _fake_candidate(page=1)
    activity = _make_activity_record(page_num=1)

    persist_molecule_candidates(
        str(library_root),
        doc_id="doc-x",
        candidates=[candidate],  # type: ignore[arg-type]
        activity_records=[activity],
    )

    db = DatabaseManager.get(str(library_root))
    with db.mol_conn() as conn:
        row = conn.execute(
            "SELECT activity, activity_type, units FROM molecules WHERE mol_id = ?",
            ("CCO",),
        ).fetchone()
    assert row is not None
    assert row["activity"] is not None and abs(row["activity"] - 12.5) < 0.01
    assert row["activity_type"] == "IC50"
    assert row["units"] == "nM"

    with db.mol_conn() as conn:
        ev = conn.execute(
            "SELECT kind, role FROM evidence WHERE canonical_smiles = ? AND kind = 'table'",
            ("CCO",),
        ).fetchall()
    assert len(ev) == 1
    assert ev[0]["role"] == "activity_data"


def test_persist_molecule_candidates_skips_mismatched_page(tmp_path: Path) -> None:
    """When the molecule is on a different page than the activity, no activity
    is written -- page-proximity is the linkage rule."""
    library_root = tmp_path / "library"
    library_root.mkdir(parents=True, exist_ok=True)

    candidate = _fake_candidate(page=5)
    activity = _make_activity_record(page_num=1)

    persist_molecule_candidates(
        str(library_root),
        doc_id="doc-y",
        candidates=[candidate],  # type: ignore[arg-type]
        activity_records=[activity],
    )

    db = DatabaseManager.get(str(library_root))
    with db.mol_conn() as conn:
        row = conn.execute(
            "SELECT activity FROM molecules WHERE mol_id = ?", ("CCO",)
        ).fetchone()
    assert row is not None
    assert row["activity"] is None  # page mismatch

    with db.mol_conn() as conn:
        ev = conn.execute(
            "SELECT COUNT(*) as c FROM evidence WHERE kind = 'table'"
        ).fetchone()
    assert ev["c"] == 0


def test_persist_molecule_candidates_back_compat_no_activity(tmp_path: Path) -> None:
    """Calling persist_molecule_candidates without activity_records is a no-op
    for activity writes (regression guard for the conn=None path)."""
    library_root = tmp_path / "library"
    library_root.mkdir(parents=True, exist_ok=True)

    candidate = _fake_candidate(page=1)
    persist_molecule_candidates(
        str(library_root),
        doc_id="doc-z",
        candidates=[candidate],  # type: ignore[arg-type]
    )

    db = DatabaseManager.get(str(library_root))
    with db.mol_conn() as conn:
        row = conn.execute(
            "SELECT activity FROM molecules WHERE mol_id = ?", ("CCO",)
        ).fetchone()
    assert row is not None
    assert row["activity"] is None


def test_extract_activities_from_document_async_offloads_to_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The async wrapper runs the sync extractor in asyncio.to_thread."""
    calls: list[tuple[object, ...]] = []

    async def _fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return []

    monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

    result = asyncio.run(
        extract_activities_from_document_async(str(tmp_path / "in.md"), "doc-x")
    )
    assert result == []
    assert len(calls) == 1
    assert calls[0][0] is extract_activities_from_document
