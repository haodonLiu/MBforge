"""Unit tests for the extract_activities pipeline stage and persistence wiring.

Covers the behavior contract:

1. Successful extraction writes activity columns + a kind='table' evidence row.
2. The stage emits a progress + complete event pair.
3. LLM failure is recoverable — pipeline finishes, molecules are still persisted.
4. A document with no tables is a no-op (no evidence rows).
5. Page-mismatch between molecule and activity → no activity is written.
6. Back-compat: omitting activity_records leaves existing behavior unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from mbforge.core.database import DatabaseManager
from mbforge.pipeline.extract_activities import (
    ActivityRecord,
    extract_activities_from_document,
)
from mbforge.pipeline.persist_molecules import persist_molecule_candidates
from mbforge.pipeline.runner import run_pipeline
from mbforge.pipeline.stage_result import PipelineErrorCode


def _mixed_density() -> MagicMock:
    d = MagicMock()
    d.doc_kind = "mixed"
    d.page_count = 2
    d.pages_needing_ocr = 0
    d.avg_text_density = 100.0
    return d


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


def _write_molecode(
    input_path: str, pages: Any, candidates: Any, output_path: str
) -> None:
    Path(output_path).write_text(
        Path(input_path).read_text(encoding="utf-8"), encoding="utf-8"
    )


def _copy_reorganized(input_path: str, output_path: str, **kwargs: Any) -> None:
    table_md = "<!-- PAGE 1 -->\n| Cmpd | IC50 (nM) |\n|---|---|\n| 1 | 12.5 |\n\n"
    Path(output_path).write_text(table_md, encoding="utf-8")


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


def test_extract_activities_writes_to_molecules_table(
    sample_pdf: Path, tmp_path: Path
) -> None:
    """When the LLM table parser returns a record on the same page as a molecule,
    the molecules row's activity/activity_type/units columns are populated and
    an evidence(kind='table') row is inserted in the same molecules.db."""
    library_root = tmp_path / "library"
    library_root.mkdir(parents=True, exist_ok=True)

    events: list[dict] = []

    def _capture(event: Any) -> None:
        events.append({"stage": event.stage, "event": event.event, "data": event.data})

    candidate = _fake_candidate(page=1)
    activity = _make_activity_record(page_num=1)

    with (
        patch(
            "mbforge.pipeline.classify.classify_density",
            return_value=_mixed_density(),
        ),
        patch(
            "mbforge.pipeline.extract_molecules.extract_molecules_from_pdf",
            return_value=[],
        ),
        patch(
            "mbforge.pipeline.runner._enrich_molecules",
            return_value={
                "molecule_count": 1,
                "rejected_count": 0,
                "pending_review_count": 0,
                "candidates": [candidate],
            },
        ),
        patch(
            "mbforge.pipeline.organizer.insert_molecode_blocks",
            side_effect=_write_molecode,
        ),
        patch(
            "mbforge.pipeline.organizer.reorganize_with_llm",
            side_effect=_copy_reorganized,
        ),
        patch(
            "mbforge.pipeline.extract_activities.extract_activities_from_document",
            return_value=[activity],
        ),
        patch(
            "mbforge.openkb.adapter.OpenKBAdapter.index_markdown",
            return_value="sample_doc_openkb",
        ),
        patch(
            "mbforge.openkb.adapter.OpenKBAdapter.compile_wiki",
            return_value=None,
        ),
    ):
        run_pipeline(
            str(sample_pdf),
            str(library_root),
            doc_id="sample_doc",
            on_progress=_capture,
        )

    db = DatabaseManager.get(str(library_root))
    with db.mol_conn() as conn:
        row = conn.execute(
            "SELECT activity, activity_type, units FROM molecules WHERE mol_id = ?",
            ("CCO",),
        ).fetchone()
    assert row is not None, "molecule row missing"
    assert row["activity"] is not None and abs(row["activity"] - 12.5) < 0.01
    assert row["activity_type"] == "IC50"
    assert row["units"] == "nM"

    with db.mol_conn() as conn:
        ev_rows = conn.execute(
            "SELECT kind, role, source_type FROM evidence WHERE canonical_smiles = ?",
            ("CCO",),
        ).fetchall()
    kinds = {r["kind"] for r in ev_rows}
    assert "table" in kinds
    table_ev = [r for r in ev_rows if r["kind"] == "table"][0]
    assert table_ev["role"] == "activity_data"
    assert table_ev["source_type"] == "llm_extraction"


def test_extract_activities_emits_stage_event(sample_pdf: Path, tmp_path: Path) -> None:
    """The stage emits progress + complete events keyed by stage='extract_activities'."""
    library_root = tmp_path / "library"
    library_root.mkdir(parents=True, exist_ok=True)

    events: list[dict] = []

    def _capture(event: Any) -> None:
        events.append({"stage": event.stage, "event": event.event, "data": event.data})

    with (
        patch(
            "mbforge.pipeline.classify.classify_density",
            return_value=_mixed_density(),
        ),
        patch(
            "mbforge.pipeline.extract_molecules.extract_molecules_from_pdf",
            return_value=[],
        ),
        patch(
            "mbforge.pipeline.runner._enrich_molecules",
            return_value={
                "molecule_count": 0,
                "rejected_count": 0,
                "pending_review_count": 0,
                "candidates": [],
            },
        ),
        patch(
            "mbforge.pipeline.organizer.insert_molecode_blocks",
            side_effect=_write_molecode,
        ),
        patch(
            "mbforge.pipeline.organizer.reorganize_with_llm",
            side_effect=_copy_reorganized,
        ),
        patch(
            "mbforge.pipeline.extract_activities.extract_activities_from_document",
            return_value=[_make_activity_record(page_num=1)],
        ),
        patch(
            "mbforge.openkb.adapter.OpenKBAdapter.index_markdown",
            return_value="sample_doc_openkb",
        ),
        patch(
            "mbforge.openkb.adapter.OpenKBAdapter.compile_wiki",
            return_value=None,
        ),
    ):
        run_pipeline(
            str(sample_pdf),
            str(library_root),
            doc_id="sample_doc",
            on_progress=_capture,
        )

    stage_events = [e for e in events if e["stage"] == "extract_activities"]
    event_kinds = [e["event"] for e in stage_events]
    assert "progress" in event_kinds
    assert "complete" in event_kinds


def test_extract_activities_recoverable_on_llm_failure(
    sample_pdf: Path, tmp_path: Path
) -> None:
    """An exception in extract_activities_from_document is recoverable — the
    pipeline finishes and molecule rows are still persisted (unaffected)."""
    library_root = tmp_path / "library"
    library_root.mkdir(parents=True, exist_ok=True)

    events: list[dict] = []

    def _capture(event: Any) -> None:
        events.append({"stage": event.stage, "event": event.event, "data": event.data})

    candidate = _fake_candidate(page=1)

    with (
        patch(
            "mbforge.pipeline.classify.classify_density",
            return_value=_mixed_density(),
        ),
        patch(
            "mbforge.pipeline.extract_molecules.extract_molecules_from_pdf",
            return_value=[],
        ),
        patch(
            "mbforge.pipeline.runner._enrich_molecules",
            return_value={
                "molecule_count": 1,
                "rejected_count": 0,
                "pending_review_count": 0,
                "candidates": [candidate],
            },
        ),
        patch(
            "mbforge.pipeline.organizer.insert_molecode_blocks",
            side_effect=_write_molecode,
        ),
        patch(
            "mbforge.pipeline.organizer.reorganize_with_llm",
            side_effect=_copy_reorganized,
        ),
        patch(
            "mbforge.pipeline.extract_activities.extract_activities_from_document",
            side_effect=RuntimeError("LLM down"),
        ),
        patch(
            "mbforge.openkb.adapter.OpenKBAdapter.index_markdown",
            return_value="sample_doc_openkb",
        ),
        patch(
            "mbforge.openkb.adapter.OpenKBAdapter.compile_wiki",
            return_value=None,
        ),
    ):
        result = run_pipeline(
            str(sample_pdf),
            str(library_root),
            doc_id="sample_doc",
            on_progress=_capture,
        )

    assert result.doc_id == "sample_doc"
    warning_events = [
        e
        for e in events
        if e["event"] == "warning" and e["stage"] == "extract_activities"
    ]
    assert len(warning_events) >= 1
    assert (
        warning_events[0]["data"].get("error_code")
        == PipelineErrorCode.ACTIVITY_EXTRACTION_FAILED
    )

    # Molecules were still persisted (recovery worked).
    db = DatabaseManager.get(str(library_root))
    with db.mol_conn() as conn:
        row = conn.execute(
            "SELECT mol_id FROM molecules WHERE mol_id = ?", ("CCO",)
        ).fetchone()
    assert row is not None, (
        "molecule persistence should not be affected by recoverable activity failure"
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
    is written — page-proximity is the linkage rule."""
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
