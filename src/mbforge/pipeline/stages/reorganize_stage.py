"""Stage 3d: LLM-based semantic text reorganization + optional Popo enhancement."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from ...core.artifact import ArtifactResolver
from ...utils.config import load_global_config
from ...utils.helpers import ensure_dir
from ...utils.logger import get_logger
from ..context import PipelineContext
from ..stage_result import PipelineErrorCode, StageResult

logger = get_logger("mbforge.pipeline.stages.reorganize")


def _ensure_heading_exists(md_path: Path, doc_id: str) -> None:
    """Ensure ``md_path`` has at least one markdown heading.

    PageIndex's ``MarkdownParser`` requires ``#`` headings to build a tree
    structure; files without headings cause ``build_index()`` to raise
    ``Processing failed``. Prepends a root heading when needed.
    """
    content = md_path.read_text(encoding="utf-8")
    if not re.search(r"^#{1,6}\s", content, re.MULTILINE):
        title = doc_id or "Document Extracted Content"
        heading = f"# {title}\n\n"
        md_path.write_text(heading + content, encoding="utf-8")
        logger.info("Prepended # heading %r for PageIndex compatibility", title)


class ReorganizeStage:
    """Stage 3d: Reorganize text with LLM + optional Popo post-processing."""

    def execute(self, ctx: PipelineContext) -> StageResult:
        """Reorganize markdown with LLM, optionally enhance with MinerU-Popo.

        Reads:
            ctx.enriched_md_path: Path
            ctx.density: DensityClassification
            ctx.candidates: list[NormalizedMolecule]

        Writes:
            ctx.final_md_path: Path (storage/{doc_id}/reorganized.md)
        """
        # Prepare final output path
        resolver = ArtifactResolver(ctx.library_root)
        storage_dir = resolver.storage_dir(ctx.doc_id)
        ensure_dir(storage_dir)
        ctx.final_md_path = resolver.reorganized_md(ctx.doc_id)

        # Optional MinerU-Popo post-processing (before reorganization)
        self._try_popo_enhancement(ctx)

        # LLM reorganization
        try:
            if ctx.density.doc_kind != "text_only" or ctx.candidates:
                from ..organizer import reorganize_with_llm

                llm_cfg = load_global_config().llm
                reorganize_model = llm_cfg.effective_model
                reorganize_with_llm(
                    str(ctx.enriched_md_path),
                    str(ctx.final_md_path),
                    model=reorganize_model,
                )
                logger.info("Text reorganized for %s", ctx.doc_id)
            else:
                # Skip reorganization for text_only docs without molecules

                shutil.copy2(str(ctx.enriched_md_path), str(ctx.final_md_path))
                logger.info("Reorganization skipped for %s (text_only, no molecules)", ctx.doc_id)

            # Ensure at least one # heading exists for PageIndex compatibility
            _ensure_heading_exists(ctx.final_md_path, ctx.doc_id)

            # Copy source PDF to storage
            self._copy_source_pdf(ctx, resolver)

            return StageResult(
                stage="reorganize",
                status="success",
                message="Text reorganized",
            )

        except Exception as e:
            logger.error("LLM reorganization failed for %s: %s", ctx.doc_id, e)
            return StageResult(
                stage="reorganize",
                status="error",
                message=f"LLM reorganization failed: {e}",
                error_code=PipelineErrorCode.LLM_REORGANIZE_FAILED,
                recoverable=True,
                context={"exception_type": type(e).__name__, "detail": str(e)},
            )

    def _try_popo_enhancement(self, ctx: PipelineContext) -> None:
        """Optional: Enhance markdown with MinerU-Popo if enabled."""
        try:
            cfg = load_global_config()
            if not cfg.popo.enabled:
                return

            from ...backends import popo as _popo

            if not _popo.popo_installed():
                logger.warning("popo.enabled=true but MinerU-Popo not installed")
                return

            logger.info("Running MinerU-Popo post-processing for %s", ctx.doc_id)
            pre_md = Path(ctx.enriched_md_path).read_text(encoding="utf-8")
            post_md = _popo.popo_postprocess_markdown(pre_md)

            if post_md and post_md != pre_md:
                Path(ctx.enriched_md_path).write_text(post_md, encoding="utf-8")
                logger.info("MinerU-Popo post-processing applied for %s", ctx.doc_id)
            else:
                logger.warning("MinerU-Popo returned no change for %s", ctx.doc_id)

        except Exception as popo_exc:
            # Popo is optional, never crash the pipeline
            logger.warning("MinerU-Popo step failed for %s: %s", ctx.doc_id, popo_exc)

    def _copy_source_pdf(self, ctx: PipelineContext, resolver: ArtifactResolver) -> None:
        """Copy source PDF to storage/{doc_id}/source.pdf for frontend preview."""
        try:
            source_pdf = resolver.source_pdf(ctx.doc_id)
            if ctx.pdf_path.resolve() != source_pdf.resolve():
                shutil.copy2(str(ctx.pdf_path), str(source_pdf))
        except Exception as pdf_copy_exc:
            # Non-fatal: pipeline can continue without source.pdf in storage
            logger.warning("Failed to copy source PDF for %s: %s", ctx.doc_id, pdf_copy_exc)
