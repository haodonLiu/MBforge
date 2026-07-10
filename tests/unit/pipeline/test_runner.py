"""Unit tests for pipeline runner stage handling and error codes."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from mbforge.pipeline.runner import run_pipeline
from mbforge.pipeline.stage_result import PipelineErrorCode


def _mixed_density() -> MagicMock:
    """Return a density classification that triggers molecule extraction."""
    d = MagicMock()
    d.doc_kind = "mixed"
    d.page_count = 2
    d.pages_needing_ocr = 0
    d.avg_text_density = 100.0
    return d


def test_pipeline_aborts_on_fatal_persist_error(
    sample_pdf: Path, tmp_path: Path
) -> None:
    """A failure in the persist_mols stage is fatal and aborts the pipeline."""
    library_root = tmp_path / "library"
    library_root.mkdir(parents=True, exist_ok=True)

    fake_candidate = MagicMock()
    fake_candidate.status = "pending"
    fake_candidate.canonical_smiles = "CCO"
    fake_candidate.esmiles = "CCO"
    fake_candidate.name = ""
    fake_candidate.sources = ["image"]
    fake_candidate.detections = [
        MagicMock(bbox=(0, 0, 1, 1), page=0, image_path="/tmp/c.png", confidence=0.9)
    ]

    def _copy_reorganized(input_path: str, output_path: str, **kwargs) -> None:
        Path(output_path).write_text(
            Path(input_path).read_text(encoding="utf-8"), encoding="utf-8"
        )

    def _write_molecode(
        input_path: str, pages: Any, candidates: Any, output_path: str
    ) -> None:
        Path(output_path).write_text(
            Path(input_path).read_text(encoding="utf-8"), encoding="utf-8"
        )

    events: list[dict] = []

    def _capture(event) -> None:
        events.append({"stage": event.stage, "event": event.event, "data": event.data})

    with (
        patch(
            "mbforge.pipeline.classify.classify_density", return_value=_mixed_density()
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
                "candidates": [fake_candidate],
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
            "mbforge.openkb.adapter.OpenKBAdapter.index_markdown",
            return_value="sample_doc_openkb",
        ),
        patch(
            "mbforge.openkb.adapter.OpenKBAdapter.compile_wiki",
            return_value=None,
        ),
        patch(
            "mbforge.pipeline.persist_molecules.persist_molecule_candidates",
            side_effect=RuntimeError("disk full"),
        ),
        pytest.raises(RuntimeError, match="disk full"),
    ):
        run_pipeline(
            str(sample_pdf),
            str(library_root),
            doc_id="sample_doc",
            on_progress=_capture,
        )

    error_events = [e for e in events if e["event"] == "error"]
    assert len(error_events) >= 1
    assert error_events[0]["stage"] == "persist_mols"
    assert (
        error_events[0]["data"].get("error_code")
        == PipelineErrorCode.PERSIST_MOLECULES_FAILED
    )


def test_pipeline_continues_on_recoverable_reorganize_error(
    sample_pdf: Path, tmp_path: Path
) -> None:
    """A failure in LLM reorganization is recoverable; the pipeline completes."""
    library_root = tmp_path / "library"
    library_root.mkdir(parents=True, exist_ok=True)

    events: list[dict] = []

    def _capture(event) -> None:
        events.append({"stage": event.stage, "event": event.event, "data": event.data})

    with (
        patch(
            "mbforge.pipeline.classify.classify_density", return_value=_mixed_density()
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
        ),
        patch(
            "mbforge.pipeline.organizer.reorganize_with_llm",
            side_effect=RuntimeError("ollama unreachable"),
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
        e for e in events if e["event"] == "warning" and e["stage"] == "reorganize"
    ]
    assert len(warning_events) >= 1
    assert (
        warning_events[0]["data"].get("error_code")
        == PipelineErrorCode.LLM_REORGANIZE_FAILED
    )
    assert warning_events[0]["data"].get("recoverable") is True


def test_pipeline_emits_stage_result_context_on_error(
    sample_pdf: Path, tmp_path: Path
) -> None:
    """Error events include exception type and detail for diagnostics."""
    library_root = tmp_path / "library"
    library_root.mkdir(parents=True, exist_ok=True)

    events: list[dict] = []

    def _capture(event) -> None:
        events.append({"stage": event.stage, "event": event.event, "data": event.data})

    with (
        patch(
            "mbforge.pipeline.classify.classify_density", return_value=_mixed_density()
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
        ),
        patch(
            "mbforge.pipeline.organizer.reorganize_with_llm",
            side_effect=RuntimeError("model down"),
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

    warning = next(
        e for e in events if e["event"] == "warning" and e["stage"] == "reorganize"
    )
    assert warning["data"]["exception_type"] == "RuntimeError"
    assert "model down" in warning["data"]["detail"]
