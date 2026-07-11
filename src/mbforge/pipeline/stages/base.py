"""Base protocol for pipeline stage executors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..context import PipelineContext
    from ..stage_result import StageResult


@runtime_checkable
class StageExecutor(Protocol):
    """Protocol for pipeline stage executors.

    Each stage implements:
    - execute(ctx) → StageResult
    - Reads from ctx, modifies ctx in-place, returns result

    Example:
        class ExtractStage:
            def execute(self, ctx: PipelineContext) -> StageResult:
                from ..extract_text import extract_pdf_text
                ctx.extracted = extract_pdf_text(str(ctx.pdf_path), ...)
                return StageResult(stage="extract", status="success", ...)
    """

    def execute(self, ctx: PipelineContext) -> StageResult:
        """Execute this pipeline stage.

        Args:
            ctx: Shared pipeline context (read + write)

        Returns:
            StageResult with status/message/error_code

        Raises:
            Exception: Fatal errors that should abort the pipeline
        """
        ...
