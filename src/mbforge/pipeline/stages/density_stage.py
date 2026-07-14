"""Stage 2: Classify document density (text_only / mixed / image_only)."""

from __future__ import annotations

from ...utils.logger import get_logger
from ..context import PipelineContext
from ..stage_result import PipelineErrorCode, StageResult

logger = get_logger("mbforge.pipeline.stages.density")


class DensityStage:
    """Stage 2: Classify document as text_only / mixed / image_only."""

    def execute(self, ctx: PipelineContext) -> StageResult:
        """Classify document density to decide whether to skip molecule detection.

        Reads:
            ctx.extracted: ExtractedDocument

        Writes:
            ctx.density: DensityClassification
        """
        if ctx.extracted is None:
            logger.error("Density stage run without extracted document for %s", ctx.doc_id)
            return StageResult(
                stage="density",
                status="error",
                message="Missing extracted document",
                error_code=PipelineErrorCode.MISSING_CONTEXT,
                recoverable=False,
            )

        try:
            from ..classify import classify_density

            ctx.density = classify_density(ctx.extracted.pages)

            logger.info(
                "Density: %s (avg=%.2f, %d/%d pages need OCR)",
                ctx.density.doc_kind,
                ctx.density.avg_text_density,
                ctx.density.pages_needing_ocr,
                ctx.density.page_count,
            )

            return StageResult(
                stage="density",
                status="success",
                message=f"Density: {ctx.density.doc_kind} ({ctx.density.pages_needing_ocr}/{ctx.density.page_count} OCR)",
                context={
                    "doc_kind": ctx.density.doc_kind,
                    "avg_text_density": ctx.density.avg_text_density,
                    "pages_needing_ocr": ctx.density.pages_needing_ocr,
                },
            )

        except Exception as e:
            logger.error("Density classification failed for %s: %s", ctx.doc_id, e)
            return StageResult(
                stage="density",
                status="error",
                message=f"Density classification failed: {e}",
                recoverable=False,
                context={"exception_type": type(e).__name__, "detail": str(e)},
            )
