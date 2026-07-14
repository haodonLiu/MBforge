"""Stage 3a-3c: Rough Markdown + Detect Molecules + Insert MoleCode.

Combines three tightly-coupled steps into one stage to avoid
intermediate file juggling.
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import NotRequired, TypedDict

from ...utils.logger import get_logger
from ..context import PipelineContext
from ..stage_result import PipelineErrorCode, StageResult

logger = get_logger("mbforge.pipeline.stages.markdown")


class MoleculeDetectionResult(TypedDict):
    """Shape of the dict returned by ``MarkdownStage._detect_molecules``.

    - ``candidates`` is always present.
    - Counts (``molecule_count``, ``rejected_count``) are always present.
    - Optional fields surface the path the detection took: ``skipped`` +
      ``reason`` for short-circuits, ``error``/``error_code`` for failures,
      ``sources``/``pending_review_count``/``total_candidates`` for success.
    """

    candidates: list
    molecule_count: int
    rejected_count: int
    skipped: NotRequired[bool]
    reason: NotRequired[str]
    error: NotRequired[str]
    error_code: NotRequired[str]
    sources: NotRequired[list[str]]
    pending_review_count: NotRequired[int]
    total_candidates: NotRequired[int]



class MarkdownStage:
    """Stage 3: Rough MD + Detect Molecules + Insert MoleCode blocks."""

    def execute(self, ctx: PipelineContext) -> StageResult:
        """Write rough markdown, detect molecules, insert MoleCode blocks.

        Reads:
            ctx.extracted: ExtractedDocument
            ctx.density: DensityClassification

        Writes:
            ctx.rough_md_path: Path
            ctx.enriched_md_path: Path
            ctx.molecule_stats: dict
            ctx.candidates: list[NormalizedMolecule]
        """
        if ctx.extracted is None:
            logger.error("Markdown stage run without extracted document for %s", ctx.doc_id)
            return StageResult(
                stage="markdown",
                status="error",
                message="Missing extracted document",
                error_code=PipelineErrorCode.MISSING_CONTEXT,
                recoverable=False,
            )

        # 3a: Write rough markdown
        logger.info("Writing rough markdown for %s", ctx.doc_id)
        from ..extract_text import write_rough_markdown

        _fd, _temp_str = tempfile.mkstemp(suffix=".md")
        os.close(_fd)
        ctx.rough_md_path = Path(_temp_str)
        write_rough_markdown(ctx.extracted.pages, str(ctx.rough_md_path))

        # 3b: Detect molecules
        logger.info("Detecting molecules for %s", ctx.doc_id)
        ctx.molecule_stats = self._detect_molecules(ctx)
        ctx.candidates = ctx.molecule_stats.get("candidates", [])
        molecule_count = ctx.molecule_stats.get("molecule_count", 0)

        if ctx.molecule_stats.get("skipped"):
            logger.info(
                "Molecule detection skipped for %s: %s",
                ctx.doc_id,
                ctx.molecule_stats.get("reason"),
            )

        # 3c: Insert MoleCode blocks
        logger.info("Inserting MoleCode blocks for %s", ctx.doc_id)
        _fd, _temp_str = tempfile.mkstemp(suffix=".md")
        os.close(_fd)
        ctx.enriched_md_path = Path(_temp_str)
        if ctx.candidates:
            from ..organizer import insert_molecode_blocks

            insert_molecode_blocks(
                str(ctx.rough_md_path),
                ctx.extracted.pages,
                ctx.candidates,
                str(ctx.enriched_md_path),
            )
        else:
            # No molecules to insert — copy rough md as-is
            shutil.copy2(str(ctx.rough_md_path), str(ctx.enriched_md_path))

        return StageResult(
            stage="markdown",
            status="success",
            message=f"Processed {molecule_count} molecules",
            context={
                "molecule_count": molecule_count,
                "rejected_count": ctx.molecule_stats.get("rejected_count", 0),
                "skipped": ctx.molecule_stats.get("skipped", False),
            },
        )

    def _detect_molecules(self, ctx: PipelineContext) -> MoleculeDetectionResult:
        """Internal: molecule detection logic (extracted from _enrich_molecules)."""
        from ..extract_molecules import extract_molecules_from_pdf
        from ..normalize import normalize_molecules

        try:
            image_results = extract_molecules_from_pdf(
                str(ctx.pdf_path),
                str(ctx.library_root),
                ctx.doc_id,
            )
        except Exception as e:
            logger.warning("Molecule image extraction failed: %s", e)
            return {
                "molecule_count": 0,
                "rejected_count": 0,
                "skipped": True,
                "reason": f"extraction_failed: {e}",
                "error_code": PipelineErrorCode.MOLDET_UNAVAILABLE,
                "candidates": [],
            }

        if not image_results:
            return {
                "molecule_count": 0,
                "rejected_count": 0,
                "skipped": True,
                "reason": "no candidates",
                "candidates": [],
            }

        try:
            normalized = normalize_molecules(image_results)
        except Exception as e:
            logger.warning("Molecule normalization failed: %s", e)
            return {
                "molecule_count": 0,
                "rejected_count": 0,
                "error": f"normalization failed: {e}",
                "error_code": PipelineErrorCode.MOLECULE_NORMALIZATION_FAILED,
                "candidates": [],
            }

        pending = [n for n in normalized if n.status == "pending"]
        pending_review = [n for n in normalized if n.status == "pending_review"]
        rejected = [n for n in normalized if n.status == "rejected"]
        sources: set[str] = set()
        for n in normalized:
            sources.update(n.sources)

        return {
            "molecule_count": len(pending) + len(pending_review),
            "rejected_count": len(rejected),
            "pending_review_count": len(pending_review),
            "total_candidates": len(normalized),
            "sources": sorted(sources),
            "candidates": normalized,
        }
