"""Document CRUD endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from ..core.library import LibraryStore
from ..models.documents import (
    DocumentDeleteRequest,
    DocumentDeleteResponse,
    DocumentListRequest,
    DocumentListResponse,
    DocumentReingestRequest,
    DocumentReingestResponse,
)
from ..pipeline.runner import run_pipeline
from ..routers._path_utils import resolve_library_root
from ..utils.helpers import NotFoundError, ValidationError
from ..utils.logger import get_logger

logger = get_logger("mbforge.documents_router")

router = APIRouter()


@router.post("/list")
async def doc_list(body: DocumentListRequest) -> DocumentListResponse:
    root = resolve_library_root(body.library_root)
    if not root:
        raise ValidationError("library_root is required")
    store = LibraryStore.get(str(root))
    docs = store.list_documents()
    return DocumentListResponse(documents=docs)


@router.post("/delete")
async def doc_delete(body: DocumentDeleteRequest) -> DocumentDeleteResponse:
    root = resolve_library_root(body.library_root)
    if not body.doc_id:
        raise ValidationError("doc_id is required")
    store = LibraryStore.get(str(root))
    store.delete_document(body.doc_id)
    return DocumentDeleteResponse()


@router.post("/reingest")
async def doc_reingest(body: DocumentReingestRequest) -> DocumentReingestResponse:
    root = resolve_library_root(body.library_root)
    if not body.doc_id:
        raise ValidationError("doc_id is required")
    store = LibraryStore.get(str(root))
    file_path = store.resolve_file(body.doc_id)
    if not file_path:
        raise NotFoundError("document not found", detail=f"doc_id={body.doc_id}")
    await asyncio.to_thread(run_pipeline, file_path, str(root), body.doc_id)
    return DocumentReingestResponse()
