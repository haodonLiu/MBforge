"""Stage 3d-1: Extract activity data from reorganized markdown tables."""

from __future__ import annotations

from ...utils.config import load_global_config
from ...utils.logger import get_logger
from ..context import PipelineContext
from ..stage_result import StageResult

logger = get_logger("mbforge.pipeline.stages.activity")


def _activity_llm_model() -> str:
    """Return the configured LLM model name for activity extraction.

    Reads ``AppConfig.llm.model`` (same source as ReorganizeStage) and falls
    back to ``"gpt-4o-mini"`` if config cannot be loaded or ``model`` is empty.
    """
    default = "gpt-4o-mini"
    try:
        cfg = load_global_config()
        return cfg.llm.model or default
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read LLM config for activity stage: %s", exc)
        return default


class ActivityStage:
    """Stage 3d-1: Extract IC50/Ki/EC50 activity data from tables."""

    def execute(self, ctx: PipelineContext) -> StageResult:
        """Extract activity data from reorganized markdown tables.

        Reads:
            ctx.final_md_path: Path

        Writes:
            ctx.activity_records: list[ActivityRecord]
        """
        if not ctx.final_md_path or not ctx.final_md_path.exists():
            logger.warning("No reorganized markdown found for %s, skipping activity extraction", ctx.doc_id)
            ctx.activity_records = []
            return StageResult(
                stage="extract_activities",
                status="warning",
                message="No reorganized markdown, skipping activity extraction",
                recoverable=True,
            )

        try:
            from ..extract_activities import extract_activities_from_document

            ctx.activity_records = extract_activities_from_document(
                str(ctx.final_md_path),
                ctx.doc_id,
                llm_model=_activity_llm_model(),
            )

            logger.info("Extracted %d activity records from %s", len(ctx.activity_records), ctx.doc_id)

            return StageResult(
                stage="extract_activities",
                status="success",
                message=f"Extracted {len(ctx.activity_records)} activity records",
                context={"activity_count": len(ctx.activity_records)},
            )

        except Exception as e:
            # Activity extraction failure is recoverable — molecules can still be persisted
            logger.warning("Activity extraction failed for %s: %s", ctx.doc_id, e)
            ctx.activity_records = []
            return StageResult(
                stage="extract_activities",
                status="warning",
                message=f"Activity extraction failed: {e}",
                recoverable=True,
                context={"exception_type": type(e).__name__, "detail": str(e)},
            )
