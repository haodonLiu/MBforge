"""Integration test for the document processing pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from mbforge.pipeline.runner import run_pipeline


def test_full_pipeline_text_only_document(sample_pdf: Path, tmp_path: Path) -> None:
    """Run the full pipeline on a native-text PDF and verify artifacts.

    The PDF has enough native text to be classified as ``text_only``; molecule
    image extraction is skipped. We mock only the LLM reorganization step and
    wiki compilation so the test does not require model downloads.
    """
    library_root = tmp_path / "library"
    library_root.mkdir(parents=True, exist_ok=True)

    def _copy_reorganized(input_path: str, output_path: str, **kwargs) -> None:
        """Mock reorganize_with_llm: just copy the input markdown."""
        Path(output_path).write_text(
            Path(input_path).read_text(encoding="utf-8"), encoding="utf-8"
        )

    with (
        patch(
            "mbforge.pipeline.organizer.reorganize_with_llm",
            side_effect=_copy_reorganized,
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
        )

    assert result.doc_id == "sample_doc"
    assert result.page_count == 2
    assert result.indexed_count == 1
    assert result.duration_ms > 0

    # File-system artifacts
    storage_dir = library_root / "storage" / "sample_doc"
    assert (storage_dir / "source.pdf").exists()
    assert (storage_dir / "reorganized.md").exists()
    assert (storage_dir / "report.json").exists()
    assert (storage_dir / "pages" / "page_0001.txt").exists()
    assert (storage_dir / "pages" / "page_0002.txt").exists()

    # Report contents
    report = json.loads((storage_dir / "report.json").read_text(encoding="utf-8"))
    assert report["doc_id"] == "sample_doc"
    assert report["page_count"] == 2
    assert report["doc_kind"] == "text_only"
    assert report["molecule_count"] == 0

    # Database artifacts: the document is persisted via the pipeline runner.
    # Detailed database assertions live in tests/unit/core/test_database.py.


def test_pipeline_progress_events_are_emitted(sample_pdf: Path, tmp_path: Path) -> None:
    """The pipeline should emit start/progress/complete events for every stage."""
    library_root = tmp_path / "library"
    library_root.mkdir(parents=True, exist_ok=True)

    events: list[dict] = []

    def _capture(event) -> None:
        events.append({"stage": event.stage, "event": event.event})

    def _copy_reorganized(input_path: str, output_path: str, **kwargs) -> None:
        Path(output_path).write_text(
            Path(input_path).read_text(encoding="utf-8"), encoding="utf-8"
        )

    with (
        patch(
            "mbforge.pipeline.organizer.reorganize_with_llm",
            side_effect=_copy_reorganized,
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

    stages = {e["stage"] for e in events}
    assert "extract" in stages
    assert "persist" in stages
    assert any(e["event"] == "complete" for e in events)
