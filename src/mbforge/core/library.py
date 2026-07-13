"""LibraryStore — unified data store for the Zotero-style library.

Manages a single `library.db` in `{library_root}/.mbforge/` and a storage
directory per imported PDF under `{library_root}/storage/{doc_id}/`. All
paths go through ``LibraryLayout`` and ``ArtifactResolver``.
"""

from __future__ import annotations

import contextlib
import hashlib
import shutil
import sqlite3
import uuid
from pathlib import Path

from ..models.library import CollectionInfo, CollectionNode, DocumentInfo
from ..utils.helpers import ConflictError, MBForgeError, NotFoundError, ensure_dir
from ..utils.logger import get_logger
from .artifact import ArtifactResolver
from .layout import LibraryLayout
from .path_utils import sanitize_upload_filename

logger = get_logger("mbforge.core.library")

_LIBRARY_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    file_name TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    md5 TEXT NOT NULL,
    page_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    source TEXT DEFAULT 'import',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS collections (
    collection_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (parent_id) REFERENCES collections(collection_id)
);

CREATE TABLE IF NOT EXISTS collection_members (
    collection_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    added_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (collection_id, doc_id),
    FOREIGN KEY (collection_id) REFERENCES collections(collection_id),
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    stage TEXT,
    progress_pct REAL DEFAULT 0,
    error TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
"""  # fmt: skip

# Instance cache: avoid re-initializing the same library root
_store_cache: dict[str, LibraryStore] = {}


class LibraryStore:
    """Single-library data store — documents, collections, tasks, and molecules."""

    def __init__(self, library_root: str | Path) -> None:
        self._root = Path(library_root).resolve()
        self._layout = LibraryLayout(self._root)
        self._resolver = ArtifactResolver(self._root)
        self._db_path = self._layout.database_path
        self._initialized = False

    @classmethod
    def get(cls, library_root: str | Path) -> LibraryStore:
        """Get cached LibraryStore singleton for the given root."""
        key = str(Path(library_root).resolve())
        if key not in _store_cache:
            _store_cache[key] = cls(library_root)
        return _store_cache[key]

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        ensure_dir(self._root)
        self._layout.ensure_metadata_dir()
        self._init_db()
        self._initialized = True

    def _init_db(self) -> None:
        """Create library.db with all tables."""
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.executescript(_LIBRARY_SCHEMA)
            from .database import DatabaseManager

            conn.executescript(DatabaseManager.molecule_schema())
            conn.commit()
            logger.info("Library DB initialized at %s", self._db_path)
        finally:
            conn.close()

    # ── Documents ────────────────────────────────────────────────

    def add_document(
        self, file_path: str | Path, title: str = ""
    ) -> DocumentInfo:
        """Copy an existing on-disk file into library storage and register it.

        Raises MBForgeError(404) if file_path is missing,
        MBForgeError(409) if md5 already exists,
        MBForgeError(507) if file copy fails.
        """
        self._ensure_initialized()
        src = Path(file_path).resolve()
        if not src.is_file():
            raise NotFoundError("File not found", detail=str(src))
        return self._register(src, title)

    def add_uploaded_file(
        self, content: bytes, filename: str, title: str = ""
    ) -> DocumentInfo:
        """Persist a browser-uploaded file payload and register it as a document.

        The DB record is committed *before* the file is exposed on disk. If the
        disk write fails, the DB row is removed so the library never references
        a missing file.

        Computes md5 from the in-memory bytes; rejects empty content; raises
        MBForgeError(409) on md5 collision, MBForgeError(507) if disk write fails.
        """
        self._ensure_initialized()
        if not content:
            raise MBForgeError("Empty file", detail=filename)
        if not filename:
            raise MBForgeError("Missing filename")

        safe_filename = sanitize_upload_filename(filename)

        # Reject duplicate imports by content hash (computed before write)
        md5 = hashlib.md5(content).hexdigest()
        existing = self._get_doc_by_md5(md5)
        if existing is not None:
            raise ConflictError(
                "Document already imported",
                detail=f"MD5 collision with doc_id={existing}",
            )

        doc_id = str(uuid.uuid4())
        safe_title = title.strip() if title else Path(safe_filename).stem
        storage_path = f"{doc_id}/{safe_filename}"
        storage_subdir = self._resolver.storage_dir(doc_id)
        dest = storage_subdir / safe_filename

        # 1. Commit the DB record first so the library never references a file
        #    that has not been successfully written.
        self._insert_document_row(doc_id, safe_title, safe_filename, storage_path, md5)

        # 2. Write the file. On failure, roll back the DB record and remove any
        #    partial artifacts so we do not leave an orphan reference.
        try:
            ensure_dir(storage_subdir)
            dest.write_bytes(content)
        except (OSError, PermissionError) as e:
            self._delete_document_row(doc_id)
            if dest.exists():
                with contextlib.suppress(OSError):
                    dest.unlink()
            if storage_subdir.exists() and not any(storage_subdir.iterdir()):
                with contextlib.suppress(OSError):
                    storage_subdir.rmdir()
            raise MBForgeError("Failed to store file", detail=str(e)) from e

        logger.info("Uploaded document registered: %s (id=%s)", safe_title, doc_id)
        return DocumentInfo(
            doc_id=doc_id,
            title=safe_title,
            file_name=safe_filename,
            page_count=0,
            status="pending",
            created_at="",
        )

    def _register(self, src: Path, title: str) -> DocumentInfo:
        """Shared helper used by add_document (existing path) and add_uploaded_file.

        Performs md5 dedup, commits the documents row, then copies the file into
        storage. If the copy fails, the DB row is removed.
        """
        md5 = self._compute_md5(src)
        existing = self._get_doc_by_md5(md5)
        if existing is not None:
            raise ConflictError(
                "Document already imported",
                detail=f"MD5 collision with doc_id={existing}",
            )

        doc_id = str(uuid.uuid4())
        safe_title = title.strip() if title else src.stem
        storage_path = f"{doc_id}/{src.name}"
        storage_subdir = self._resolver.storage_dir(doc_id)
        dest = storage_subdir / src.name

        # 1. Commit the DB record first.
        self._insert_document_row(doc_id, safe_title, src.name, storage_path, md5)

        # 2. Copy the file; roll back the DB record on failure.
        try:
            ensure_dir(storage_subdir)
            shutil.copy2(str(src), str(dest))
        except (OSError, PermissionError) as e:
            self._delete_document_row(doc_id)
            if dest.exists():
                with contextlib.suppress(OSError):
                    dest.unlink()
            if storage_subdir.exists() and not any(storage_subdir.iterdir()):
                with contextlib.suppress(OSError):
                    storage_subdir.rmdir()
            raise MBForgeError("Failed to store file", detail=str(e)) from e

        logger.info("Document added: %s (id=%s)", safe_title, doc_id)
        return DocumentInfo(
            doc_id=doc_id,
            title=safe_title,
            file_name=src.name,
            page_count=0,
            status="pending",
            created_at="",
        )

    def _insert_document_row(
        self,
        doc_id: str,
        title: str,
        file_name: str,
        storage_path: str,
        md5: str,
    ) -> None:
        """Insert a documents row and commit the transaction."""
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute(
                """INSERT INTO documents (doc_id, title, file_name, storage_path, md5)
                   VALUES (?, ?, ?, ?, ?)""",
                (doc_id, title, file_name, storage_path, md5),
            )
            conn.commit()
        finally:
            conn.close()

    def _delete_document_row(self, doc_id: str) -> None:
        """Remove a documents row and any collection membership."""
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM collection_members WHERE doc_id = ?", (doc_id,))
            conn.commit()
        finally:
            conn.close()

    def get_document(self, doc_id: str) -> DocumentInfo | None:
        self._ensure_initialized()
        conn = sqlite3.connect(str(self._db_path))
        try:
            row = conn.execute(
                "SELECT doc_id, title, file_name, page_count, status, created_at "
                "FROM documents WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
            if row is None:
                return None
            return DocumentInfo(
                doc_id=row[0],
                title=row[1],
                file_name=row[2],
                page_count=row[3],
                status=row[4],
                created_at=row[5],
            )
        finally:
            conn.close()

    def delete_document(self, doc_id: str) -> None:
        """Remove storage dir + DB row atomically (best-effort).

        The storage directory is moved to a temporary trash location before the
        DB transaction is committed. If the DB delete fails, the storage is
        restored to its original location so the library remains consistent.
        """
        self._ensure_initialized()
        storage_subdir = self._resolver.storage_dir(doc_id)
        trash_path: Path | None = None

        # 1. Move storage out of the live tree before committing the DB delete.
        if storage_subdir.exists():
            trash_dir = self._layout.metadata_dir / "trash"
            ensure_dir(trash_dir)
            trash_path = trash_dir / f"{doc_id}_{uuid.uuid4().hex}"
            try:
                shutil.move(str(storage_subdir), str(trash_path))
            except (OSError, PermissionError) as e:
                raise MBForgeError(
                    "Failed to remove document storage", detail=str(e)
                ) from e

        # 2. Commit the DB delete.
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            conn.execute(
                "DELETE FROM collection_members WHERE doc_id = ?", (doc_id,)
            )
            conn.commit()
        except Exception:
            # DB delete failed: restore storage from trash so we do not lose
            # files while the row still exists.
            if trash_path is not None and trash_path.exists():
                try:
                    shutil.move(str(trash_path), str(storage_subdir))
                except OSError as restore_exc:
                    logger.error(
                        "Failed to restore storage for %s after DB delete failure: %s",
                        doc_id,
                        restore_exc,
                    )
            raise
        finally:
            conn.close()

        # 3. Storage is no longer referenced; delete the trash copy.
        if trash_path is not None and trash_path.exists():
            try:
                shutil.rmtree(trash_path, ignore_errors=True)
            except OSError as cleanup_exc:
                logger.warning(
                    "Failed to remove trashed storage for %s: %s",
                    doc_id,
                    cleanup_exc,
                )
        logger.info("Document deleted: %s", doc_id)

    def list_documents(
        self, collection_id: str | None = None
    ) -> list[DocumentInfo]:
        self._ensure_initialized()
        conn = sqlite3.connect(str(self._db_path))
        try:
            if collection_id:
                rows = conn.execute(
                    """SELECT d.doc_id, d.title, d.file_name, d.page_count,
                              d.status, d.created_at
                       FROM documents d
                       JOIN collection_members cm ON d.doc_id = cm.doc_id
                       WHERE cm.collection_id = ?
                       ORDER BY d.created_at DESC""",
                    (collection_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT doc_id, title, file_name, page_count, status, created_at "
                    "FROM documents ORDER BY created_at DESC"
                ).fetchall()
            return [
                DocumentInfo(
                    doc_id=r[0],
                    title=r[1],
                    file_name=r[2],
                    page_count=r[3],
                    status=r[4],
                    created_at=r[5],
                )
                for r in rows
            ]
        finally:
            conn.close()

    def search_documents(self, query: str) -> list[DocumentInfo]:
        self._ensure_initialized()
        conn = sqlite3.connect(str(self._db_path))
        try:
            like = f"%{query}%"
            rows = conn.execute(
                "SELECT doc_id, title, file_name, page_count, status, created_at "
                "FROM documents WHERE title LIKE ? OR file_name LIKE ? "
                "ORDER BY created_at DESC",
                (like, like),
            ).fetchall()
            return [
                DocumentInfo(
                    doc_id=r[0],
                    title=r[1],
                    file_name=r[2],
                    page_count=r[3],
                    status=r[4],
                    created_at=r[5],
                )
                for r in rows
            ]
        finally:
            conn.close()

    def update_document_status(self, doc_id: str, status: str) -> None:
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute(
                "UPDATE documents SET status = ?, updated_at = datetime('now') "
                "WHERE doc_id = ?",
                (status, doc_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ── Collections ──────────────────────────────────────────────

    def create_collection(
        self, name: str, parent_id: str | None = None
    ) -> CollectionInfo:
        self._ensure_initialized()
        if parent_id is not None:
            self._require_collection(parent_id)

        collection_id = str(uuid.uuid4())
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute(
                "INSERT INTO collections (collection_id, name, parent_id) "
                "VALUES (?, ?, ?)",
                (collection_id, name, parent_id),
            )
            conn.commit()
        finally:
            conn.close()

        logger.info("Collection created: %s (id=%s)", name, collection_id)
        return CollectionInfo(
            collection_id=collection_id,
            name=name,
            parent_id=parent_id,
            doc_count=0,
        )

    def delete_collection(self, collection_id: str) -> None:
        self._ensure_initialized()
        self._require_collection(collection_id)
        conn = sqlite3.connect(str(self._db_path))
        try:
            # Remove membership rows (but not the docs themselves)
            conn.execute(
                "DELETE FROM collection_members WHERE collection_id = ?",
                (collection_id,),
            )
            # Reparent children to parent of deleted collection
            parent = conn.execute(
                "SELECT parent_id FROM collections WHERE collection_id = ?",
                (collection_id,),
            ).fetchone()
            parent_id = parent[0] if parent else None
            conn.execute(
                "UPDATE collections SET parent_id = ? WHERE parent_id = ?",
                (parent_id, collection_id),
            )
            conn.execute(
                "DELETE FROM collections WHERE collection_id = ?",
                (collection_id,),
            )
            conn.commit()
        finally:
            conn.close()
        logger.info("Collection deleted: %s", collection_id)

    def get_collection_tree(self) -> list[CollectionNode]:
        self._ensure_initialized()
        conn = sqlite3.connect(str(self._db_path))
        try:
            rows = conn.execute(
                """SELECT c.collection_id, c.name, c.parent_id,
                          (SELECT COUNT(*) FROM collection_members cm
                           WHERE cm.collection_id = c.collection_id) AS doc_count
                   FROM collections c
                   ORDER BY c.sort_order, c.name"""
            ).fetchall()
            all_items: list[CollectionInfo] = [
                CollectionInfo(
                    collection_id=r[0],
                    name=r[1],
                    parent_id=r[2],
                    doc_count=r[3],
                )
                for r in rows
            ]
            children_of: dict[str | None, list[CollectionNode]] = {}
            for item in all_items:
                node = CollectionNode(
                    collection_id=item.collection_id,
                    name=item.name,
                    parent_id=item.parent_id,
                    doc_count=item.doc_count,
                )
                parent_key = item.parent_id
                if parent_key not in children_of:
                    children_of[parent_key] = []
                children_of[parent_key].append(node)

            roots = children_of.get(None, [])
            for node in all_items:
                cid = node.collection_id
                if cid in children_of:
                    found = self._find_in_tree(roots, cid)
                    if found is not None:
                        found.children = children_of[cid]
            return roots
        finally:
            conn.close()

    def add_to_collection(self, collection_id: str, doc_id: str) -> None:
        self._ensure_initialized()
        self._require_collection(collection_id)
        self._require_doc(doc_id)
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute(
                "INSERT OR IGNORE INTO collection_members (collection_id, doc_id) "
                "VALUES (?, ?)",
                (collection_id, doc_id),
            )
            conn.commit()
        finally:
            conn.close()

    def remove_from_collection(
        self, collection_id: str, doc_id: str
    ) -> None:
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute(
                "DELETE FROM collection_members "
                "WHERE collection_id = ? AND doc_id = ?",
                (collection_id, doc_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ── Path helpers ─────────────────────────────────────────────

    def db_path(self) -> str:
        return str(self._db_path)

    def storage_path(self, doc_id: str) -> str:
        return str(self._resolver.storage_dir(doc_id))

    def resolve_file(self, doc_id: str) -> str | None:
        """Resolve the original PDF file path for a document."""
        self._ensure_initialized()
        conn = sqlite3.connect(str(self._db_path))
        try:
            row = conn.execute(
                "SELECT file_name FROM documents WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
            if row is None:
                return None
            pdf_path = self._resolver.storage_dir(doc_id) / row[0]
            return str(pdf_path) if pdf_path.exists() else None
        finally:
            conn.close()

    def doc_count(self) -> int:
        self._ensure_initialized()
        conn = sqlite3.connect(str(self._db_path))
        try:
            row = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    # ── Internals ────────────────────────────────────────────────

    @staticmethod
    def _compute_md5(path: Path) -> str:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def _get_doc_by_md5(self, md5: str) -> str | None:
        conn = sqlite3.connect(str(self._db_path))
        try:
            row = conn.execute(
                "SELECT doc_id FROM documents WHERE md5 = ?", (md5,)
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def _require_collection(self, collection_id: str) -> None:
        conn = sqlite3.connect(str(self._db_path))
        try:
            row = conn.execute(
                "SELECT 1 FROM collections WHERE collection_id = ?",
                (collection_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "Collection not found",
                    detail=f"collection_id={collection_id}",
                )
        finally:
            conn.close()

    def _require_doc(self, doc_id: str) -> None:
        conn = sqlite3.connect(str(self._db_path))
        try:
            row = conn.execute(
                "SELECT 1 FROM documents WHERE doc_id = ?",
                (doc_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(
                    "Document not found",
                    detail=f"doc_id={doc_id}",
                )
        finally:
            conn.close()

    def _find_in_tree(
        self, nodes: list[CollectionNode], target_id: str
    ) -> CollectionNode | None:
        for n in nodes:
            if n.collection_id == target_id:
                return n
            child = self._find_in_tree(n.children, target_id)
            if child is not None:
                return child
        return None
