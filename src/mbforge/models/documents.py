"""Pydantic models for document endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .library import DocumentInfo


class DocumentListRequest(BaseModel):
    """Request body for listing documents."""

    library_root: str | None = Field(
        default=None,
        description="Library root path. Falls back to global config when omitted.",
    )


class DocumentListResponse(BaseModel):
    """Response body for listing documents."""

    success: bool = True
    documents: list[DocumentInfo] = Field(default_factory=list)


class DocumentDeleteRequest(BaseModel):
    """Request body for deleting a document."""

    library_root: str | None = Field(
        default=None,
        description="Library root path. Falls back to global config when omitted.",
    )
    doc_id: str = Field(default="", description="Document identifier to delete.")


class DocumentDeleteResponse(BaseModel):
    """Response body for deleting a document."""

    success: bool = True


class DocumentReingestRequest(BaseModel):
    """Request body for re-ingesting a document."""

    library_root: str | None = Field(
        default=None,
        description="Library root path. Falls back to global config when omitted.",
    )
    doc_id: str = Field(default="", description="Document identifier to re-ingest.")


class DocumentReingestResponse(BaseModel):
    """Response body for re-ingesting a document."""

    success: bool = True
    message: str = "reingest completed"
