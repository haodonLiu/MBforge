"""Stage 1: Extract text from PDF (PyMuPDF + OCR fallback)."""

from __future__ import annotations

from ...utils.logger import get_logger
from ..context import PipelineContext
from ..stage_result import PipelineErrorCode, StageResult

logger = get_logger("mbforge.pipeline.stages.extract")


class ExtractStage:
    """Stage 1: Extract text from PDF with OCR fallback."""

    def execute(self, ctx: PipelineContext) -> StageResult:
        """Extract text from PDF using PyMuPDF + OCR chain.

        Writes:
            ctx.extracted: ExtractedDocument
        """
        try:
            from ..extract_text import extract_pdf_text

            ctx.extracted = extract_pdf_text(
                str(ctx.pdf_path),
                ocr_fallback=True,
                ocr_config=ctx.ocr_config,
            )

            logger.info(
                "Extracted %d pages (%d chars) from %s",
                ctx.extracted.page_count,
                len(ctx.extracted.raw_text),
                ctx.doc_id,
            )

            return StageResult(
                stage="extract",
                status="success",
                message=f"Extracted {ctx.extracted.page_count} pages ({len(ctx.extracted.raw_text)} chars)",
                context={
                    "page_count": ctx.extracted.page_count,
                    "parser": ctx.extracted.parser,
                },
            )

        except Exception as e:
            logger.error("Text extraction failed for %s: %s", ctx.doc_id, e)
            return StageResult(
                stage="extract",
                status="error",
                message=f"Text extraction failed: {e}",
                error_code=PipelineErrorCode.PDF_PARSE_ERROR,
                recoverable=False,
                context={"exception_type": type(e).__name__, "detail": str(e)},
            )
