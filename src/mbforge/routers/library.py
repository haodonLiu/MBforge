"""Library API router — unified document library (Zotero-style).

Prefix: /api/v1/library
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from ..utils.config import load_global_config, update_settings
from ..utils.helpers import MBForgeError
from ..utils.logger import get_logger
from ..utils.paths import GLOBAL_DATA_DIR

logger = get_logger("mbforge.library_router")

router = APIRouter()


def _resolve_library_root(body: dict | None = None) -> str:
    """Resolve library_root from body, config, or default."""
    cfg = load_global_config()
    explicit = (body or {}).get("library_root", "")
    if explicit:
        return explicit
    if cfg.library_root:
        return cfg.library_root
    return str(GLOBAL_DATA_DIR / "library")


@router.get("/status")
async def library_status() -> dict:
    """Get library configuration status."""
    root = _resolve_library_root()
    configured = bool(load_global_config().library_root)
    try:
        from ..core.library import LibraryStore

        store = LibraryStore.get(root)
        doc_count = store.doc_count()
    except Exception:
        doc_count = 0
    return {
        "configured": configured,
        "root": root,
        "doc_count": doc_count,
    }


@router.post("/import")
async def library_import(body: dict) -> dict:
    """Import a PDF into the library."""
    file_path = body.get("file_path", "")
    title = body.get("title", "")
    root = _resolve_library_root(body)
    if not file_path:
        return {"success": False, "error": "file_path required"}

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
        doc = store.add_document(file_path, title=title)
    except MBForgeError as e:
        return {"success": False, "error": e.message, "detail": e.detail}
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
