"""Pydantic models for the unified library (Zotero-style)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DocumentInfo(BaseModel):
    """A single imported document in the library."""

    doc_id: str
    title: str
    file_name: str
    page_count: int = 0
    status: str = "pending"  # pending | indexing | ready | error
    created_at: str = ""


class CollectionInfo(BaseModel):
    """A collection (group) in the library tree."""

    collection_id: str
    name: str
    parent_id: str | None = None
    doc_count: int = 0


class CollectionNode(CollectionInfo):
    """A collection node with nested children for tree rendering."""

    children: list[CollectionNode] = []


class LibraryStatus(BaseModel):
    """Library configuration status."""

    configured: bool
    root: str
    doc_count: int


# ---- Request models ----

class LibraryListDocumentsRequest(BaseModel):
    library_root: str | None = None
    collection_id: str | None = None


class LibraryDeleteDocumentRequest(BaseModel):
    library_root: str | None = None
    doc_id: str = ""


class LibraryCreateCollectionRequest(BaseModel):
    library_root: str | None = None
    name: str = ""
    parent_id: str | None = None


class LibraryCollectionIdRequest(BaseModel):
    library_root: str | None = None
    collection_id: str = ""


class LibraryCollectionDocumentRequest(BaseModel):
    library_root: str | None = None
    collection_id: str
    doc_id: str


class LibraryConfigureRequest(BaseModel):
    root: str = ""


# ---- Response models ----

class LibraryImportResponse(BaseModel):
    success: bool = True
    document: dict[str, Any]


class LibraryDocumentsResponse(BaseModel):
    documents: list[dict[str, Any]] = []


class LibraryCollectionResponse(BaseModel):
    success: bool = True
    collection: dict[str, Any]


class LibraryCollectionsResponse(BaseModel):
    collections: list[dict[str, Any]] = []


class LibraryConfigureResponse(BaseModel):
    success: bool = True
    root: str


class LibrarySuccessResponse(BaseModel):
    success: bool = True
