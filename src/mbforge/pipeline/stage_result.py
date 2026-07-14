"""Structured stage results and error codes for the document pipeline.

Every pipeline stage returns a ``StageResult``. Errors are categorized by a
machine-readable ``error_code`` and a ``recoverable`` flag so the runner can
decide whether to continue (skip the stage) or abort the whole pipeline, and
so the frontend can show actionable messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


class PipelineErrorCode:
    """Machine-readable error codes emitted by pipeline stages."""

    PDF_PARSE_ERROR = "PDF_PARSE_ERROR"
    OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
    MOLDET_UNAVAILABLE = "MOLDET_UNAVAILABLE"
    MOLSCRIBE_FAILED = "MOLSCRIBE_FAILED"
    MOLECULE_NORMALIZATION_FAILED = "MOLECULE_NORMALIZATION_FAILED"
    LLM_REORGANIZE_FAILED = "LLM_REORGANIZE_FAILED"
    ACTIVITY_EXTRACTION_FAILED = "ACTIVITY_EXTRACTION_FAILED"
    OPENKB_INDEX_FAILED = "OPENKB_INDEX_FAILED"
    OPENKB_WIKI_FAILED = "OPENKB_WIKI_FAILED"
    PERSIST_MOLECULES_FAILED = "PERSIST_MOLECULES_FAILED"
    REGISTER_LINKS_FAILED = "REGISTER_LINKS_FAILED"
    PERSIST_DOCUMENT_FAILED = "PERSIST_DOCUMENT_FAILED"
    MISSING_CONTEXT = "MISSING_CONTEXT"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass
class StageResult:
    """Outcome of a single pipeline stage.

    Attributes:
        stage: Stage name (matches keys in ``STAGE_PCT``).
        status: ``success``, ``warning`` (stage skipped but pipeline continues),
            or ``error`` (pipeline aborts).
        message: Human-readable description.
        error_code: Machine-readable code when status is not ``success``.
        recoverable: If ``True`` the runner logs a warning and continues; if
            ``False`` the runner emits an error event and aborts.
        context: Extra JSON-serializable data (e.g., exception type, counts).
    """

    stage: str
    status: Literal["success", "warning", "error"]
    message: str
    error_code: str | None = None
    recoverable: bool = False
    context: dict[str, Any] = field(default_factory=dict)
