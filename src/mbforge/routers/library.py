"""Library API router — unified document library (Zotero-style).

Prefix: /api/v1/library
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response

from ..utils.config import load_global_config, update_settings
from ..utils.helpers import MBForgeError
from ..utils.logger import get_logger

logger = get_logger("mbforge.library_router")

router = APIRouter()

_SAFE_DOC_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def _validate_doc_id(doc_id: str) -> None:
    if not doc_id or not _SAFE_DOC_ID_RE.match(doc_id):
        raise HTTPException(400, f"invalid doc_id: {doc_id}")


def _resolve_doc_artifact(root: str, doc_id: str, *parts: str) -> Path:
    _validate_doc_id(doc_id)
    base = (Path(root) / "storage" / doc_id).resolve()
    target = (base.joinpath(*parts)).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise HTTPException(400, f"path traversal detected: {doc_id}/{parts}") from exc
    return target


def _resolve_crop_artifact(root: str, doc_id: str, rel_path: str) -> Path:
    _validate_doc_id(doc_id)
    crop_root = (Path(root) / ".mbforge" / "crops" / doc_id).resolve()
    target = (crop_root / rel_path).resolve()
    try:
        target.relative_to(crop_root)
    except ValueError as exc:
        raise HTTPException(400, f"invalid rel_path: {rel_path}") from exc
    return target


def _resolve_library_root(body: dict | None = None) -> str:
    r"""Resolve library_root from body, config, or default (~\/mbforge).

    Priority: explicit body param > stored settings.json value > ~/mbforge.
    This default is intentionally under the user home (not the OS app-data
    directory) so imported PDFs are easy to find and back up.
    """
    cfg = load_global_config()
    explicit = (body or {}).get("library_root", "")
    if explicit:
        return explicit
    if cfg.library_root:
        return cfg.library_root
    return str(Path.home() / "mbforge")


@router.get("/status")
async def library_status() -> dict:
    """Get library configuration status.

    Reports `configured: true` whenever the resolved library root either was
    explicitly configured OR can be auto-created from the default (~/mbforge).
    """
    root = _resolve_library_root()
    try:
        Path(root).mkdir(parents=True, exist_ok=True)
        from ..core.library import LibraryStore

        store = LibraryStore.get(root)
        doc_count = store.doc_count()
        configured = True
    except (OSError, PermissionError):
        configured = False
        doc_count = 0
    return {
        "configured": configured,
        "root": root,
        "doc_count": doc_count,
    }


class _MissingUploadError(MBForgeError):
    status_code = 400
    error_code = "missing_upload"


@router.post("/import")
async def library_import(
    file: UploadFile | None = None,
    title: str = Form(""),
    library_root: str | None = Form(None),
) -> dict:
    """Import a PDF (or other document) into the library via multipart upload.

    Browser sends the raw bytes; backend streams to {library_root}/storage/
    {doc_id}/{filename} and registers the document in the library DB.
    """
    if file is None:
        raise _MissingUploadError(
            "No file provided", detail="multipart file field is required"
        )
    root = _resolve_library_root({"library_root": library_root} if library_root else None)

    # Validate root is writable
    try:
        Path(root).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return {
            "success": False,
            "error": "Cannot access library directory",
            "detail": str(e),
        }

    from ..core.library import LibraryStore

    store = LibraryStore.get(root)
    try:
        content = await file.read()
        doc = store.add_uploaded_file(
            content=content,
            filename=file.filename or "",
            title=title,
        )
    except MBForgeError as e:
        return {"success": False, "error": e.message, "detail": e.detail}
    except Exception as e:
        logger.exception("Unexpected import error: %s", e)
        return {"success": False, "error": "Import failed", "detail": str(e)}
    return {"success": True, "document": doc.model_dump()}


@router.post("/documents")
async def library_list_documents(body: dict) -> dict:
    """List documents, optionally filtered by collection."""
    collection_id = body.get("collection_id")
    root = _resolve_library_root(body)
    from ..core.library import LibraryStore

    store = LibraryStore.get(root)
    docs = store.list_documents(collection_id)
    return {"documents": [d.model_dump() for d in docs]}


@router.post("/documents/delete")
async def library_delete_document(body: dict) -> dict:
    """Delete a document by doc_id."""
    doc_id = body.get("doc_id", "")
    root = _resolve_library_root(body)
    if not doc_id:
        return {"success": False, "error": "doc_id required"}
    from ..core.library import LibraryStore

    store = LibraryStore.get(root)
    store.delete_document(doc_id)
    return {"success": True}


@router.get("/documents/{doc_id}/file")
async def library_get_document_file(doc_id: str, library_root: str | None = None) -> FileResponse:
    """Stream the original PDF bytes for a library document.

    Used by the PDF viewer iframe after import; URL is library-root agnostic
    beyond a `library_root` query param if a non-default root is configured.
    """
    root = _resolve_library_root({"library_root": library_root} if library_root else None)
    from ..core.library import LibraryStore
    from ..utils.helpers import MBForgeError

    class _DocumentNotFoundError(MBForgeError):
        status_code = 404
        error_code = "document_not_found"

    store = LibraryStore.get(root)
    pdf_path = store.resolve_file(doc_id)
    if pdf_path is None:
        raise _DocumentNotFoundError("Document file not found", detail=f"doc_id={doc_id}")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=Path(pdf_path).name,
    )


# ---------------------------------------------------------------------------
# Pipeline artifact endpoints — reorganized md, per-page text, crops,
# report.json, PageIndex indexed markdown. The frontend DocumentViewer
# fetches all of these.
# ---------------------------------------------------------------------------


@router.get("/documents/{doc_id}/reorganized")
async def library_get_reorganized(doc_id: str, library_root: str | None = None) -> PlainTextResponse:
    """Return the LLM-reorganized markdown for a document."""
    root = _resolve_library_root({"library_root": library_root} if library_root else None)
    p = _resolve_doc_artifact(root, doc_id, "reorganized.md")
    if not p.is_file():
        raise HTTPException(404, f"reorganized.md not found for {doc_id}")
    return PlainTextResponse(p.read_text(encoding="utf-8"))


@router.get("/documents/{doc_id}/report")
async def library_get_report(doc_id: str, library_root: str | None = None) -> Response:
    """Return the pipeline report.json for a document."""
    root = _resolve_library_root({"library_root": library_root} if library_root else None)
    p = _resolve_doc_artifact(root, doc_id, "report.json")
    if not p.is_file():
        raise HTTPException(404, f"report.json not found for {doc_id}")
    return Response(content=p.read_bytes(), media_type="application/json")


@router.get("/documents/{doc_id}/crop")
async def library_get_crop(
    doc_id: str, rel_path: str, library_root: str | None = None
) -> FileResponse:
    """Serve a single cropped molecule image.

    `rel_path` is the filename relative to `.mbforge/crops/{doc_id}/`
    (e.g. ``WO2026035726A1_20pg_page_0003_mol_0002.png``).
    """
    root = _resolve_library_root({"library_root": library_root} if library_root else None)
    target = _resolve_crop_artifact(root, doc_id, rel_path)
    if not target.is_file():
        raise HTTPException(404, f"crop not found: {rel_path}")
    return FileResponse(str(target), media_type="image/png")


@router.get("/documents/{doc_id}/indexed-md")
async def library_get_indexed_md(
    doc_id: str, library_root: str | None = None
) -> PlainTextResponse:
    """Return the PageIndex-indexed markdown for a document."""
    root = _resolve_library_root({"library_root": library_root} if library_root else None)
    _validate_doc_id(doc_id)
    p = Path(root) / ".mbforge" / "openkb" / "documents" / f"{doc_id}.md"
    if not p.is_file():
        raise HTTPException(404, f"indexed md not found for {doc_id}")
    return PlainTextResponse(p.read_text(encoding="utf-8"))


@router.get("/documents/{doc_id}/pages/{page}")
async def library_get_page_text(
    doc_id: str, page: int, library_root: str | None = None
) -> PlainTextResponse:
    """Return the per-page OCR text for a single page (1-based)."""
    root = _resolve_library_root({"library_root": library_root} if library_root else None)
    p = _resolve_doc_artifact(root, doc_id, "pages", f"page_{page:04d}.txt")
    if not p.is_file():
        raise HTTPException(404, f"page {page} text not found for {doc_id}")
    return PlainTextResponse(p.read_text(encoding="utf-8"))


@router.post("/collections/create")
async def library_create_collection(body: dict) -> dict:
    """Create a new collection (group)."""
    name = body.get("name", "")
    parent_id = body.get("parent_id")
    root = _resolve_library_root(body)
    if not name:
        return {"success": False, "error": "name required"}
    from ..core.library import LibraryStore

    store = LibraryStore.get(root)
    try:
        col = store.create_collection(name, parent_id)
    except MBForgeError as e:
        return {"success": False, "error": e.message, "detail": e.detail}
    return {"success": True, "collection": col.model_dump()}


@router.post("/collections/list")
async def library_list_collections(body: dict) -> dict:
    """List collections as a tree."""
    root = _resolve_library_root(body)
    from ..core.library import LibraryStore

    store = LibraryStore.get(root)
    tree = store.get_collection_tree()
    return {"collections": [n.model_dump() for n in tree]}


@router.post("/collections/delete")
async def library_delete_collection(body: dict) -> dict:
    """Delete a collection by collection_id."""
    collection_id = body.get("collection_id", "")
    root = _resolve_library_root(body)
    if not collection_id:
        return {"success": False, "error": "collection_id required"}
    from ..core.library import LibraryStore

    store = LibraryStore.get(root)
    try:
        store.delete_collection(collection_id)
    except MBForgeError as e:
        return {"success": False, "error": e.message, "detail": e.detail}
    return {"success": True}


@router.post("/collections/add-document")
async def library_collection_add_document(body: dict) -> dict:
    """Add a document to a collection."""
    collection_id = body.get("collection_id", "")
    doc_id = body.get("doc_id", "")
    root = _resolve_library_root(body)
    if not collection_id or not doc_id:
        return {"success": False, "error": "collection_id and doc_id required"}
    from ..core.library import LibraryStore

    store = LibraryStore.get(root)
    try:
        store.add_to_collection(collection_id, doc_id)
    except MBForgeError as e:
        return {"success": False, "error": e.message, "detail": e.detail}
    return {"success": True}


@router.post("/collections/remove-document")
async def library_collection_remove_document(body: dict) -> dict:
    """Remove a document from a collection."""
    collection_id = body.get("collection_id", "")
    doc_id = body.get("doc_id", "")
    root = _resolve_library_root(body)
    if not collection_id or not doc_id:
        return {"success": False, "error": "collection_id and doc_id required"}
    from ..core.library import LibraryStore

    store = LibraryStore.get(root)
    store.remove_from_collection(collection_id, doc_id)
    return {"success": True}


@router.post("/configure")
async def library_configure(body: dict) -> dict:
    """Configure the library root directory."""
    root = body.get("root", "")
    if not root:
        return {"success": False, "error": "root required"}
    try:
        Path(root).mkdir(parents=True, exist_ok=True)
        test_file = Path(root) / ".mbforge_write_test"
        test_file.write_text("ok")
        test_file.unlink()
    except OSError as e:
        return {
            "success": False,
            "error": "Directory not writable",
            "detail": str(e),
        }
    update_settings({"library_root": root})
    return {"success": True, "root": root}
