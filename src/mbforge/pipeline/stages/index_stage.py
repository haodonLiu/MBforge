"""Stage 3e+4: PageIndex tree indexing + Wiki compilation."""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Coroutine
from typing import TypeVar

from ...utils.logger import get_logger
from ..context import PipelineContext
from ..stage_result import PipelineErrorCode, StageResult

T = TypeVar("T")
logger = get_logger("mbforge.pipeline.stages.index")

# Shared executor for the rare case where _run_async_in_sync is called while
# an event loop is already running. Using one module-level pool avoids the
# per-call ThreadPoolExecutor allocation that previously happened inside
# IndexStage.execute.
_RUN_ASYNC_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="index_stage_async"
)


def _run_async_in_sync(coro: Coroutine[..., None, T]) -> T:
    """Run an async coroutine from sync code without breaking event loops.

    - No running loop: call asyncio.run() directly.
    - Running loop (e.g. FastAPI): submit to a shared thread pool, run
      asyncio.run() there, and block on the result. This avoids both the
      "asyncio.run() cannot be called from a running loop" RuntimeError and
      the creation of a fresh ThreadPoolExecutor on every call.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    return _RUN_ASYNC_POOL.submit(lambda: asyncio.run(coro)).result()


class IndexStage:
    """Stage 3e+4: Build PageIndex tree + compile wiki summaries."""

    def execute(self, ctx: PipelineContext) -> StageResult:
        """Index markdown via PageIndex tree + compile wiki.

        Reads:
            ctx.final_md_path: Path
            ctx.extracted: ExtractedDocument
            ctx.density: DensityClassification

        Writes:
            ctx.openkb_doc_id: str
            ctx.indexed_count: int
        """
        # Stage 3e: PageIndex tree indexing
        logger.info("Building PageIndex tree for %s", ctx.doc_id)

        try:
            from ...openkb.adapter import OpenKBAdapter

            adapter = OpenKBAdapter(ctx.library_root)
            ctx.openkb_doc_id = adapter.index_markdown(ctx.final_md_path, ctx.doc_id)
            ctx.indexed_count = 1
            logger.info("PageIndex tree built: %s", ctx.openkb_doc_id)

        except Exception as e:
            logger.warning("PageIndex indexing failed for %s: %s", ctx.doc_id, e)
            ctx.openkb_doc_id = ""
            ctx.indexed_count = 0
            # Continue to wiki compilation attempt

        # Stage 4: Wiki compilation
        if ctx.openkb_doc_id:
            logger.info("Compiling wiki for %s", ctx.doc_id)
            doc_name = ctx.pdf_path.stem

            try:
                _run_async_in_sync(
                    adapter.compile_wiki(doc_name, ctx.doc_id, ctx.extracted.page_count)
                )
                logger.info("Wiki compiled for %s", ctx.doc_id)

            except Exception as e:
                logger.warning("Wiki compilation failed for %s: %s", ctx.doc_id, e)
                # Non-fatal: continue even if wiki fails

        elif ctx.density.doc_kind == "image_only":
            logger.warning(
                "Wiki compile skipped for %s (image-only doc with failed indexing)",
                ctx.doc_id,
            )

        # Return combined result
        if ctx.openkb_doc_id:
            return StageResult(
                stage="index",
                status="success",
                message=f"Indexed + wiki compiled: {ctx.openkb_doc_id}",
                context={"openkb_doc_id": ctx.openkb_doc_id},
            )
        else:
            return StageResult(
                stage="index",
                status="warning",
                message="PageIndex indexing failed",
                error_code=PipelineErrorCode.OPENKB_INDEX_FAILED,
                recoverable=True,
            )
