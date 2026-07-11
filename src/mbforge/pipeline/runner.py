"""Pipeline runner — orchestrates document processing via modular stages.

Refactored from monolithic 747-line function to stage-based architecture.
Each stage is a self-contained executor in pipeline/stages/*.py.

Stages (7 logical groups):
1. Extract: PDF text extraction (PyMuPDF + OCR fallback)
2. Density: Classify document as text_only / mixed / image_only
3. Markdown: Rough MD + Detect Molecules + Insert MoleCode
4. Reorganize: LLM semantic reorg + optional Popo enhancement
5. Activity: Extract IC50/Ki/EC50 from tables
6. Index: PageIndex tree + Wiki compilation
7. Persist: Molecules + Links + Document (single txn)
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.database import DatabaseManager
from ..utils.config import load_global_config
from ..utils.logger import get_logger
from .context import PipelineContext
from .stage_result import StageResult
from .stages import (
    ActivityStage,
    DensityStage,
    ExtractStage,
    IndexStage,
    MarkdownStage,
    PersistStage,
    ReorganizeStage,
)
from .stages.base import StageExecutor

logger = get_logger("mbforge.pipeline.runner")

# Per-stage progress percentages surfaced via _emit when task_id is set.
STAGE_PCT: dict[str, int] = {
    "extract": 10,
    "density": 18,
    "markdown": 35,  # rough_md + detect + insert merged
    "reorganize": 55,  # includes optional popo
    "extract_activities": 60,
    "index": 70,  # pageindex + wiki merged
    "persist": 100,  # persist_mols + register_links + persist_doc merged
    "pipeline": 100,
}


def _current_ocr_config() -> dict:
    """Read current ocr config from AppConfig.ocr (settings.json)."""
    try:
        cfg = load_global_config()
        return dict(cfg.ocr or {})
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read OCR config: %s", exc)
        return {}


def _is_temp_path(path: Path | None, library_root: Path | None = None) -> bool:
    """Return True if `path` is a transient scratch file outside the library.

    A path is considered persistent only when it lives under
    ``{library_root}/storage/``; everything else is treated as scratch and
    safe to delete during cleanup. This avoids mis-classifying persistent
    artifacts as transient when the library root happens to be located under
    a directory whose name contains ``temp`` or ``tmp`` (e.g. pytest tmp_path).
    """
    if path is None or library_root is None:
        return False
    storage_root = (library_root / "storage").resolve()
    try:
        path.resolve().relative_to(storage_root)
    except ValueError:
        return True
    return False


@dataclass
class PipelineEvent:
    stage: str
    event: str | None = None
    message: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class PipelineResult:
    doc_id: str
    page_count: int = 0
    indexed_count: int = 0
    parser: str = ""
    title: str = ""
    duration_ms: int = 0


ProgressCallback = Callable[[PipelineEvent], None]

# Stage registry — executed sequentially.
#
# Stage instances must remain stateless: all state lives in PipelineContext,
# not on the stage object. Any future instance attribute added here will be
# shared across concurrent pipeline invocations, so prefer constructor-time
# configuration or context fields over per-instance state.
STAGES: list[StageExecutor] = [
    ExtractStage(),
    DensityStage(),
    MarkdownStage(),
    ReorganizeStage(),
    ActivityStage(),
    IndexStage(),
    PersistStage(),
]


def run_pipeline(
    pdf_path: str,
    library_root: str,
    doc_id: str = "",
    *,
    task_id: str | None = None,
    project_root: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> PipelineResult:
    """Run the document processing pipeline via modular stages.

    Args:
        pdf_path: Path to the PDF file
        library_root: Library data directory
        doc_id: Document ID (auto-generated from filename if empty)
        task_id: Optional queue task ID for progress tracking
        project_root: Deprecated, use library_root
        on_progress: Progress callback

    Returns:
        PipelineResult with processing statistics
    """
    if library_root:
        root = Path(library_root)
    elif project_root:
        root = Path(project_root)
    else:
        raise ValueError(
            "run_pipeline requires either `library_root` or `project_root`; "
            "both were None/empty"
        )
    if not doc_id:
        doc_id = Path(pdf_path).stem

    # Initialize context
    ctx = PipelineContext(
        pdf_path=Path(pdf_path),
        library_root=root,
        doc_id=doc_id,
        task_id=task_id,
        ocr_config=_current_ocr_config(),
    )

    start_time = time.monotonic()

    def _maybe_record(
        event: str,
        message: str,
        *,
        stage: str | None = None,
        **data: Any,
    ) -> None:
        """Forward an _emit call to record_ingest_event when DB writes enabled."""
        if task_id is None:
            return
        try:
            from ..core.database import record_ingest_event

            progress_pct: int | None = STAGE_PCT.get(stage) if stage else None
            status: str | None = "processing" if event == "start" else None
            record_ingest_event(
                DatabaseManager.get(str(root)),
                task_id=task_id,
                doc_id=doc_id or None,
                stage=stage or "pipeline",
                level=event,
                message=message,
                data=data or None,
                progress_pct=progress_pct,
                status=status,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("record_ingest_event failed: %s", exc)
            try:
                from ..utils.logger import push_diagnostic

                push_diagnostic(
                    {
                        "level": "WARNING",
                        "message": f"record_ingest_event failed: {exc}",
                        "category": "pipeline.runner",
                        "error_code": "ingest_log_write_failed",
                    }
                )
            except Exception:  # pragma: no cover
                pass

    def _emit(
        event: str,
        message: str = "",
        *,
        stage: str | None = None,
        **data: Any,
    ) -> None:
        """Emit pipeline event to progress callback + logger + ingest queue."""
        if on_progress:
            on_progress(
                PipelineEvent(
                    stage=stage or "pipeline", event=event, message=message, data=data
                ),
            )
        logger.info("[%s] %s", event, message)
        _maybe_record(event, message, stage=stage, **data)

    def _emit_stage_result(result: StageResult) -> None:
        """Emit a pipeline event from a StageResult."""
        data: dict[str, Any] = dict(result.context)
        if result.error_code:
            data["error_code"] = result.error_code
        data["recoverable"] = result.recoverable
        event_name = "warning" if result.recoverable else result.status
        _emit(
            event_name,
            result.message,
            stage=result.stage,
            **data,
        )

    _emit("start", f"Processing {Path(pdf_path).name}")
    # Validate all registered stages satisfy the StageExecutor protocol
    for stage in STAGES:
        if not isinstance(stage, StageExecutor):
            raise TypeError(
                f"{type(stage).__name__} does not satisfy StageExecutor protocol"
            )
    # Execute stages sequentially
    for stage_executor in STAGES:
        stage_name = stage_executor.__class__.__name__.replace("Stage", "").lower()

        try:
            result = stage_executor.execute(ctx)

            _emit_stage_result(result)

            if result.status == "error" and not result.recoverable:
                raise RuntimeError(f"{stage_name} failed: {result.message}")

        except Exception as e:
            _emit(stage_name, f"Exception: {e}", error=str(e))
            raise

    # Clean up temporary files
    # Cleanup list: rough_md and enriched_md are always transient; final_md
    # is transient only when produced into a temp dir by ReorganizeStage
    # (otherwise it is the persistent storage/{doc_id}/reorganized.md and
    # must NOT be removed).
    _candidate_paths = [
        ctx.rough_md_path,
        ctx.enriched_md_path,
        ctx.final_md_path if _is_temp_path(ctx.final_md_path, ctx.library_root) else None,
    ]
    for temp_path in _candidate_paths:
        if temp_path is None:
            continue
        with contextlib.suppress(Exception):
            temp_path.unlink(missing_ok=True)

    ctx.duration_ms = int((time.monotonic() - start_time) * 1000)
    _emit("complete", f"Pipeline finished in {ctx.duration_ms}ms", stage="pipeline")

    return PipelineResult(
        doc_id=ctx.doc_id,
        page_count=ctx.extracted.page_count if ctx.extracted else 0,
        indexed_count=ctx.indexed_count,
        parser=ctx.extracted.parser if ctx.extracted else "",
        title=ctx.extracted.title if ctx.extracted else "",
        duration_ms=ctx.duration_ms,
    )
