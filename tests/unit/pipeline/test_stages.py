"""Unit tests for pipeline stages."""

from __future__ import annotations

import asyncio
import concurrent.futures
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mbforge.core.database import DatabaseManager
from mbforge.pipeline.context import PipelineContext
from mbforge.pipeline.runner import STAGES, _is_temp_path, run_pipeline
from mbforge.pipeline.stage_result import PipelineErrorCode, StageResult
from mbforge.pipeline.stages import (
    DensityStage,
    ExtractStage,
    IndexStage,
    MarkdownStage,
    PersistStage,
    ReorganizeStage,
)
from mbforge.pipeline.stages.activity_stage import _activity_llm_model
from mbforge.pipeline.stages.base import StageExecutor
from mbforge.pipeline.stages.index_stage import _run_async_in_sync
from mbforge.pipeline.stages.markdown_stage import MoleculeDetectionResult


class TestPipelineContext:
    """Test PipelineContext dataclass."""

    def test_context_initialization(self):
        ctx = PipelineContext(
            pdf_path=Path("/tmp/test.pdf"),
            library_root=Path("/tmp/library"),
            doc_id="test_doc",
        )
        assert ctx.pdf_path == Path("/tmp/test.pdf")
        assert ctx.library_root == Path("/tmp/library")
        assert ctx.doc_id == "test_doc"
        assert ctx.task_id is None
        assert ctx.extracted is None
        assert ctx.density is None
        assert ctx.candidates == []
        assert ctx.activity_records == []

    def test_context_with_optional_fields(self):
        ctx = PipelineContext(
            pdf_path=Path("/tmp/test.pdf"),
            library_root=Path("/tmp/library"),
            doc_id="test_doc",
            task_id="task_123",
            ocr_config={"provider": "mineru"},
        )
        assert ctx.task_id == "task_123"
        assert ctx.ocr_config == {"provider": "mineru"}


class TestStageExecutors:
    """Test stage executor protocols."""

    def test_extract_stage_has_execute_method(self):
        stage = ExtractStage()
        assert hasattr(stage, "execute")
        assert callable(stage.execute)

    def test_density_stage_has_execute_method(self):
        stage = DensityStage()
        assert hasattr(stage, "execute")
        assert callable(stage.execute)

    def test_all_stages_have_execute(self):
        stages = [
            ExtractStage(),
            DensityStage(),
            MarkdownStage(),
            ReorganizeStage(),
            IndexStage(),
            PersistStage(),
        ]
        for stage in stages:
            assert hasattr(stage, "execute")
            assert callable(stage.execute)

    def test_all_stages_satisfy_runtime_checkable_protocol(self):
        """Step 5: @runtime_checkable Protocol must accept every stage."""
        for stage in STAGES:
            assert isinstance(stage, StageExecutor), (
                f"{type(stage).__name__} should satisfy StageExecutor"
            )

    def test_nonconforming_stage_rejected_by_protocol(self):
        """Step 5: a class missing execute() must fail isinstance()."""

        class BadStage:
            pass

        assert not isinstance(BadStage(), StageExecutor)


class TestRunPipelineMissingRoot:
    """Step 3: run_pipeline must reject empty library_root."""

    def test_none_library_root_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError) as exc_info:
            run_pipeline("dummy.pdf", library_root=None)
        msg = str(exc_info.value)
        assert "library_root" in msg, msg

    def test_empty_library_root_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            run_pipeline("dummy.pdf", library_root="")

    def test_library_root_accepted(self, tmp_path):
        """When a valid library_root is given, run_pipeline must not raise ValueError."""
        # We expect it to fail later (PDF doesn't exist) but the root resolution
        # must succeed.
        lib = tmp_path / "library"
        lib.mkdir()
        with pytest.raises(Exception) as exc_info:
            run_pipeline(str(tmp_path / "nope.pdf"), library_root=str(lib))
        # Must NOT be the root-rejection ValueError
        assert not isinstance(exc_info.value, ValueError) or (
            "library_root" not in str(exc_info.value)
        )


class TestIsTempPath:
    """Step 2: cleanup helper for transient vs persistent paths."""

    def test_none_is_not_temp(self):
        assert not _is_temp_path(None)

    def test_persistent_storage_path_is_not_temp(self):
        lib = Path(r"C:\Users\admin\library")
        p = lib / "storage" / "doc_001" / "reorganized.md"
        assert not _is_temp_path(p, library_root=lib)

    def test_temp_path_detected(self):
        p = Path(r"C:\Users\admin\AppData\Local\Temp\tmp_xyz.md")
        assert _is_temp_path(p, library_root=Path(r"C:\Users\admin\library"))

    def test_path_with_temp_component_outside_storage_detected(self):
        p = Path(r"C:\some\dir\temp_xyz\reorganized.md")
        assert _is_temp_path(p, library_root=Path(r"C:\Users\admin\library"))

    def test_path_with_tmp_component_outside_storage_detected(self):
        p = Path(r"C:\some\dir\tmp_xyz\reorganized.md")
        assert _is_temp_path(p, library_root=Path(r"C:\Users\admin\library"))

    def test_path_under_temp_but_inside_library_storage_is_persistent(self):
        r"""Regression guard: pytest tmp_path lives under ``AppData\Temp``."""
        lib = Path(r"C:\Users\admin\AppData\Local\Temp\pytest-123\library")
        p = lib / "storage" / "doc_001" / "reorganized.md"
        assert not _is_temp_path(p, library_root=lib)


class TestStageNullChecks:
    """Stage executors must guard against missing upstream context."""

    def test_density_stage_requires_extracted(self, tmp_path):
        ctx = PipelineContext(
            pdf_path=tmp_path / "x.pdf",
            library_root=tmp_path,
            doc_id="t-missing",
        )
        result = DensityStage().execute(ctx)
        assert result.status == "error"
        assert result.error_code == PipelineErrorCode.MISSING_CONTEXT

    def test_markdown_stage_requires_extracted(self, tmp_path):
        ctx = PipelineContext(
            pdf_path=tmp_path / "x.pdf",
            library_root=tmp_path,
            doc_id="t-missing",
        )
        result = MarkdownStage().execute(ctx)
        assert result.status == "error"
        assert result.error_code == PipelineErrorCode.MISSING_CONTEXT

    def test_reorganize_stage_requires_density(self, tmp_path):
        ctx = PipelineContext(
            pdf_path=tmp_path / "x.pdf",
            library_root=tmp_path,
            doc_id="t-missing",
            enriched_md_path=tmp_path / "enriched.md",
        )
        result = ReorganizeStage().execute(ctx)
        assert result.status == "error"
        assert result.error_code == PipelineErrorCode.MISSING_CONTEXT

    def test_index_stage_requires_final_md(self, tmp_path):
        ctx = PipelineContext(
            pdf_path=tmp_path / "x.pdf",
            library_root=tmp_path,
            doc_id="t-missing",
        )
        result = IndexStage().execute(ctx)
        assert result.status == "error"
        assert result.error_code == PipelineErrorCode.MISSING_CONTEXT

    def test_persist_stage_requires_context(self, tmp_path):
        ctx = PipelineContext(
            pdf_path=tmp_path / "x.pdf",
            library_root=tmp_path,
            doc_id="t-missing",
        )
        result = PersistStage().execute(ctx)
        assert result.status == "error"
        assert result.error_code == PipelineErrorCode.MISSING_CONTEXT


class TestAsyncSafety:
    """Step 1: _run_async_in_sync must work both with and without a running loop."""

    def test_no_running_loop_path(self):
        async def coro():
            return 42

        assert _run_async_in_sync(coro()) == 42

    def test_inside_running_loop_path(self):
        async def outer():
            async def inner():
                await asyncio.sleep(0)
                return "in-loop"

            return _run_async_in_sync(inner())

        assert asyncio.run(outer()) == "in-loop"

    def test_exception_propagates_from_no_loop(self):
        async def coro():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            _run_async_in_sync(coro())

    def test_no_per_call_thread_pool_executor(self, monkeypatch):
        """_run_async_in_sync must not create a ThreadPoolExecutor on each call."""
        created_count = {"n": 0}
        real_executor = concurrent.futures.ThreadPoolExecutor

        def _counting_executor(*args, **kwargs):
            created_count["n"] += 1
            return real_executor(*args, **kwargs)

        monkeypatch.setattr(
            concurrent.futures, "ThreadPoolExecutor", _counting_executor
        )

        async def outer():
            async def inner():
                await asyncio.sleep(0)
                return "ok"

            return _run_async_in_sync(inner())

        assert asyncio.run(outer()) == "ok"
        assert created_count["n"] == 0


class TestExtractStage:
    """Step 11: cover ExtractStage happy path and PDF failure path."""

    def test_execute_success(self, tmp_path):
        """Mock extract_pdf_text to return a fake ExtractedDocument."""
        from mbforge.pipeline.extract_text import ExtractedDocument

        fake_doc = ExtractedDocument(raw_text="hello", page_count=1, parser="pymupdf")
        ctx = PipelineContext(
            pdf_path=tmp_path / "fake.pdf",
            library_root=tmp_path,
            doc_id="t1",
        )

        with patch("mbforge.pipeline.extract_text.extract_pdf_text", return_value=fake_doc):
            result = ExtractStage().execute(ctx)

        assert isinstance(result, StageResult)
        assert result.status == "success"
        assert ctx.extracted is fake_doc
        assert result.context["page_count"] == 1
        assert result.context["parser"] == "pymupdf"

    def test_execute_failure_returns_error_result(self, tmp_path):
        """When extract_pdf_text raises, stage returns error result (does NOT raise)."""
        ctx = PipelineContext(
            pdf_path=tmp_path / "bad.pdf",
            library_root=tmp_path,
            doc_id="t2",
        )

        with patch(
            "mbforge.pipeline.extract_text.extract_pdf_text",
            side_effect=ValueError("corrupt pdf"),
        ):
            result = ExtractStage().execute(ctx)

        assert result.status == "error"
        assert result.recoverable is False
        assert "Text extraction failed" in result.message
        assert ctx.extracted is None


class TestActivityLlmModel:
    """Step 4: activity stage must read the LLM model from AppConfig."""

    def test_returns_nonempty_string(self):
        m = _activity_llm_model()
        assert isinstance(m, str)
        assert m, "model name must not be empty"

    def test_uses_configured_model(self, tmp_path, monkeypatch):
        """When config has a different model, the helper returns it."""
        from mbforge.pipeline.stages import activity_stage as act_mod

        class _FakeLLM:
            model = "gpt-4-turbo"
            provider = "openai_compatible"
            api_key = ""
            base_url = ""
            temperature = 0.7
            max_tokens = 4096
            pageindex_threshold = 20
            language = "en"
            reorganize_model = None

        class _FakeCfg:
            llm = _FakeLLM()

        monkeypatch.setattr(act_mod, "load_global_config", lambda: _FakeCfg())
        assert _activity_llm_model() == "gpt-4-turbo"


class TestMarkdownStageTypedResult:
    """Step 6: _detect_molecules return value must conform to TypedDict."""

    def test_no_image_results_returns_no_candidates(self, tmp_path):
        """When the extractor returns nothing, the result has reason='no candidates'."""
        ctx = PipelineContext(
            pdf_path=tmp_path / "doc.pdf",
            library_root=tmp_path,
            doc_id="t3",
        )

        with patch(
            "mbforge.pipeline.extract_molecules.extract_molecules_from_pdf",
            return_value=[],
        ):
            result = MarkdownStage()._detect_molecules(ctx)

        assert isinstance(result, dict)
        assert result["candidates"] == []
        assert result["skipped"] is True
        assert result["reason"] == "no candidates"
        assert result["molecule_count"] == 0
        assert result["rejected_count"] == 0

    def test_extractor_failure_returns_error_code(self, tmp_path):
        """Extractor exceptions surface as a failure result with an error code."""
        ctx = PipelineContext(
            pdf_path=tmp_path / "doc.pdf",
            library_root=tmp_path,
            doc_id="t3b",
        )

        with patch(
            "mbforge.pipeline.extract_molecules.extract_molecules_from_pdf",
            side_effect=RuntimeError("disk full"),
        ):
            result = MarkdownStage()._detect_molecules(ctx)

        assert result["skipped"] is True
        assert "extraction_failed" in result["reason"]
        assert result["error_code"] == "MOLDET_UNAVAILABLE"

    def test_typed_dict_required_keys(self):
        """The TypedDict must be importable and have the right required keys."""
        required = MoleculeDetectionResult.__required_keys__
        assert "candidates" in required
        assert "molecule_count" in required
        assert "rejected_count" in required


class TestPersistStageCompensation:
    """Failure mid-persist must be compensated to keep DB/filesystem consistent."""

    def test_compensates_molecule_rows_when_document_write_fails(
        self, tmp_path: Path
    ) -> None:
        db = DatabaseManager.get(str(tmp_path))
        db.initialize()
        doc_id = "doc-123"
        final_md = tmp_path / "reorganized.md"
        final_md.write_text("# Doc", encoding="utf-8")
        ctx = PipelineContext(
            pdf_path=tmp_path / "x.pdf",
            library_root=tmp_path,
            doc_id=doc_id,
            extracted=MagicMock(page_count=1, pages=[]),
            density=MagicMock(doc_kind="text_only", avg_text_density=100.0),
            final_md_path=final_md,
        )
        stage = PersistStage()

        def _fake_persist_molecules(_ctx: PipelineContext) -> None:
            # Simulate a successful molecule persist by inserting doc-specific rows.
            with db.mol_conn() as conn:
                conn.execute(
                    "INSERT INTO molecules (mol_id, smiles) VALUES (?, ?)",
                    ("M1", "C"),
                )
                conn.execute(
                    "INSERT INTO molecule_detections (mol_id, doc_id, page) VALUES (?, ?, ?)",
                    ("M1", doc_id, 1),
                )
                conn.execute(
                    "INSERT INTO evidence (canonical_smiles, doc_id, kind) VALUES (?, ?, ?)",
                    ("C", doc_id, "figure"),
                )
                conn.execute(
                    "INSERT INTO text_molecule_links (doc_id, mol_id, created_at) VALUES (?, ?, ?)",
                    (doc_id, "M1", 0),
                )

        def _fail_document_persist(_ctx: PipelineContext) -> None:
            raise OSError("disk full")

        stage._persist_molecules_and_links = _fake_persist_molecules
        stage._persist_document = _fail_document_persist

        result = stage.execute(ctx)

        assert result.status == "error"
        assert result.error_code == PipelineErrorCode.PERSIST_DOCUMENT_FAILED
        assert (
            db.execute(
                "SELECT COUNT(*) AS cnt FROM molecule_detections WHERE doc_id = ?",
                (doc_id,),
                db="mol",
            )[0]["cnt"]
            == 0
        )
        assert (
            db.execute(
                "SELECT COUNT(*) AS cnt FROM evidence WHERE doc_id = ?",
                (doc_id,),
                db="mol",
            )[0]["cnt"]
            == 0
        )
        assert (
            db.execute(
                "SELECT COUNT(*) AS cnt FROM text_molecule_links WHERE doc_id = ?",
                (doc_id,),
                db="mol",
            )[0]["cnt"]
            == 0
        )

