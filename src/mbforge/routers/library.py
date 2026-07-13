"""Library API router — unified document library (Zotero-style).

Prefix: /api/v1/library
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response

from ..core.path_utils import sanitize_upload_filename
from ..utils.config import load_global_config, update_settings
from ..utils.helpers import FileAccessError, MBForgeError, ValidationError
from ..utils.logger import get_logger
from ..utils.paths import GLOBAL_APP_DIR
from ._path_utils import InvalidPathError, resolve_library_root, validate_doc_id

logger = get_logger("mbforge.library_router")

router = APIRouter()


# Path resolution delegates to ArtifactResolver (core/artifact.py). The
# router keeps thin wrappers for back-compat with existing callers; the
# ArtifactResolver is the single source of truth.
def _resolve_doc_artifact(root: str, doc_id: str, *parts: str) -> Path:
    """Resolve a path under ``storage/{doc_id}/`` via ArtifactResolver."""
    from ..core.artifact import ArtifactResolver, InvalidDocIdError

    resolver = ArtifactResolver(root)
    try:
        base = resolver.storage_dir(doc_id).resolve()
    except InvalidDocIdError as exc:
        raise HTTPException(400, str(exc)) from exc
    target = base.joinpath(*parts).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise HTTPException(400, f"path traversal detected: {doc_id}/{parts}") from exc
    return target


def _resolve_crop_artifact(root: str, doc_id: str, rel_path: str) -> Path:
    """Resolve a crop under the canonical storage layout via ArtifactResolver.

    Falls back to the legacy ``.mbforge/crops/{doc_id}/`` location if the
    canonical path does not exist; this preserves reads for libraries
    created before the 2026-07-10 storage unification. The migration
    script (``scripts/migrate_artifact_paths.py``) moves the files.
    """
    from ..core.artifact import ArtifactResolver, PathTraversalError

    resolver = ArtifactResolver(root)
    try:
        canonical = resolver.crop(doc_id, rel_path)
    except PathTraversalError as exc:
        raise InvalidPathError(f"invalid crop rel_path: {rel_path}") from exc
    if canonical.is_file():
        return canonical
    legacy = resolver.legacy_crop(doc_id, rel_path)
    if legacy.is_file():
        return legacy
    return canonical  # surface canonical for the 404 path


def _resolve_library_root(body: dict | None = None) -> str:
    r"""Resolve library_root from body, config, or default (~\/MBForge).

    Priority: explicit body param > stored settings.json value > ~/MBForge.
    The default lives inside the unified application directory so settings,
    logs and library data are co-located by default. Advanced users may set a
    separate library_root via the Settings UI.

    The returned path is validated through ``resolve_library_root`` so callers
    never receive an empty or relative root.
    """
    cfg = load_global_config()
    explicit = (body or {}).get("library_root", "")
    root = explicit or cfg.library_root or str(GLOBAL_APP_DIR)
    return str(resolve_library_root(root))


@router.get("/status")
async def library_status() -> dict:
    """Get library configuration status.

    Reports `configured: true` whenever the resolved library root either was
    explicitly configured OR can be auto-created from the default (~/MBForge).
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


class _UploadTooLargeError(MBForgeError):
    status_code = 413
    error_code = "upload_too_large"


# 200 MB cap on browser uploads. Large PDFs should be imported from the
# filesystem or streamed; keeping the cap prevents OOM on malicious clients.
_MAX_UPLOAD_BYTES = 200 * 1024 * 1024


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

    # Validate filename before reading potentially malicious payloads.
    safe_name = sanitize_upload_filename(file.filename or "")

    # Validate root is writable
    try:
        Path(root).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise FileAccessError(
            "Cannot access library directory", detail=str(e)
        ) from e

    from ..core.library import LibraryStore

    store = LibraryStore.get(root)
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise _UploadTooLargeError(
            f"Upload exceeds {_MAX_UPLOAD_BYTES} bytes", detail=safe_name
        )
    doc = store.add_uploaded_file(
        content=content,
        filename=safe_name,
        title=title,
    )
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
        raise ValidationError("doc_id is required")
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
        # Fallback for legacy/project documents stored under ``storage/{doc_id}/source.pdf``
        # but not yet registered in the unified LibraryStore DB (e.g. pre-migration
        # patents referenced by their publication number).
        from ..core.artifact import ArtifactResolver

        legacy_pdf = ArtifactResolver(root).source_pdf(doc_id)
        if legacy_pdf.is_file():
            pdf_path = str(legacy_pdf)
        else:
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
    from ..core.layout import LibraryLayout

    root = _resolve_library_root({"library_root": library_root} if library_root else None)
    validate_doc_id(doc_id)
    p = LibraryLayout(root).openkb_dir / "documents" / f"{doc_id}.md"
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
        raise ValidationError("name is required")
    from ..core.library import LibraryStore

    store = LibraryStore.get(root)
    col = store.create_collection(name, parent_id)
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
        raise ValidationError("collection_id is required")
    from ..core.library import LibraryStore

    store = LibraryStore.get(root)
    store.delete_collection(collection_id)
    return {"success": True}


@router.post("/collections/add-document")
async def library_collection_add_document(body: dict) -> dict:
    """Add a document to a collection."""
    collection_id = body.get("collection_id", "")
    doc_id = body.get("doc_id", "")
    root = _resolve_library_root(body)
    if not collection_id:
        raise ValidationError("collection_id is required")
    if not doc_id:
        raise ValidationError("doc_id is required")
    from ..core.library import LibraryStore

    store = LibraryStore.get(root)
    store.add_to_collection(collection_id, doc_id)
    return {"success": True}


@router.post("/collections/remove-document")
async def library_collection_remove_document(body: dict) -> dict:
    """Remove a document from a collection."""
    collection_id = body.get("collection_id", "")
    doc_id = body.get("doc_id", "")
    root = _resolve_library_root(body)
    if not collection_id:
        raise ValidationError("collection_id is required")
    if not doc_id:
        raise ValidationError("doc_id is required")
    from ..core.library import LibraryStore

    store = LibraryStore.get(root)
    store.remove_from_collection(collection_id, doc_id)
    return {"success": True}


@router.post("/configure")
async def library_configure(body: dict) -> dict:
    """Configure the library root directory."""
    root = body.get("root", "")
    if not root:
        raise ValidationError("root is required")
    try:
        Path(root).mkdir(parents=True, exist_ok=True)
        test_file = Path(root) / ".mbforge_write_test"
        test_file.write_text("ok")
        test_file.unlink()
    except OSError as e:
        raise FileAccessError("Directory not writable", detail=str(e)) from e
    update_settings({"library_root": root})
    return {"success": True, "root": root}
