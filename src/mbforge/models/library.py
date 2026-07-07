"""Pydantic models for the unified library (Zotero-style)."""

from __future__ import annotations

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
