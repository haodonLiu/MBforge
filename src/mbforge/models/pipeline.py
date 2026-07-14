"""Pydantic models for pipeline endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PipelineEnqueueRequest(BaseModel):
    """Request body for enqueueing a pipeline run."""

    library_root: str | None = Field(
        default=None,
        description="Library root path. Falls back to global config when omitted.",
    )
    action: str | None = Field(
        default=None,
        description="Special action, e.g. 'enqueue_unresolved'.",
    )
    file_path: str | None = Field(
        default=None,
        description="Path to the PDF to process.",
    )
    doc_id: str = Field(default="", description="Optional document identifier.")


class PipelineEnqueueResponse(BaseModel):
    """Response body for enqueueing a pipeline run."""

    success: bool = True
    task_id: str | None = Field(default=None, description="Assigned task ID.")
    enqueued: int | None = Field(
        default=None,
        description="Number of files enqueued for 'enqueue_unresolved' action.",
    )
    error: str | None = Field(default=None, description="Error message on failure.")


class PipelineProcessRequest(BaseModel):
    """Request body for synchronous pipeline processing."""

    library_root: str | None = Field(
        default=None,
        description="Library root path. Falls back to global config when omitted.",
    )
    file_path: str = Field(..., description="Path to the PDF to process.")
    doc_id: str = Field(default="", description="Optional document identifier.")


class PipelineProcessResponse(BaseModel):
    """Response body for synchronous pipeline processing."""

    success: bool = True
    task_id: str
    doc_id: str
    page_count: int
    indexed_count: int
    parser: str
    title: str
    duration_ms: int
    error: str | None = None


class PipelineQueueRequest(BaseModel):
    """Request body for fetching the ingest queue."""

    library_root: str | None = Field(
        default=None,
        description="Library root path. Falls back to global config when omitted.",
    )


class PipelineQueueResponse(BaseModel):
    """Response body for fetching the ingest queue."""

    success: bool = True
    tasks: list[dict] = Field(default_factory=list)


class PipelineQueueStatsResponse(BaseModel):
    """Response body for queue statistics."""

    success: bool = True
    stats: dict = Field(default_factory=dict)


class PipelineTaskActionResponse(BaseModel):
    """Generic response for task actions (cancel, retry, delete, etc.)."""

    success: bool = True
    cleaned: int | None = None
    logs: list[dict] | None = None
