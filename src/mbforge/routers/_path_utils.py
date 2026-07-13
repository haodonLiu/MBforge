"""Shared path-resolution helpers for FastAPI routers.

Every router that needs to turn a user-supplied ``library_root`` / ``doc_id``
into a filesystem path must go through this module so that path-traversal
attacks are rejected at a single choke point.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..core.artifact import ArtifactResolver, InvalidDocIdError
from ..core.path_utils import InvalidPathError
from ..utils.helpers import MBForgeError


class DocumentNotFoundError(MBForgeError):
    """Raised when a document resolves safely but does not exist on disk."""

    status_code = 404
    error_code = "not_found"


_SAFE_DOC_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def _ensure_inside_root(path: Path, root: Path) -> None:
    """Raise ``InvalidPathError`` if ``path`` escapes ``root``.

    Both paths are expected to be already resolved.
    """
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise InvalidPathError(
            f"path traversal detected: {path.name} escapes {root}"
        ) from exc


def resolve_library_root(library_root: str | None = None) -> Path:
    """Resolve and validate a library root, falling back to global config.

    Returns an absolute, resolved ``Path``. Raises ``InvalidPathError`` if the
    value is missing, relative, contains traversal segments, or does not match
    the configured library root. Only the active configured root (or a fallback
    to it) is accepted so requests cannot target arbitrary directories.
    """
    from ..utils.config import load_global_config

    cfg_root = load_global_config().library_root or ""
    if not library_root:
        library_root = cfg_root
    if not library_root:
        raise InvalidPathError("library_root is required")

    input_path = Path(library_root)
    if not input_path.is_absolute():
        raise InvalidPathError(f"library_root must be absolute: {library_root}")

    for seg in re.split(r"[/\\]", library_root):
        if seg in (".", ".."):
            raise InvalidPathError(
                f"path traversal detected in library_root: {library_root}"
            )

    resolved = input_path.resolve()
    cfg_resolved = Path(cfg_root).resolve() if cfg_root else resolved
    if resolved != cfg_resolved:
        raise InvalidPathError(
            f"library_root does not match configured root: {library_root}"
        )
    return resolved


def validate_doc_id(doc_id: str) -> None:
    """Raise ``InvalidPathError`` if ``doc_id`` is empty or contains separators."""
    if not doc_id or not _SAFE_DOC_ID_RE.match(doc_id):
        raise InvalidPathError(f"invalid doc_id: {doc_id!r}")


def resolve_pdf_path(
    library_root: str,
    doc_id: str,
    *,
    must_exist: bool = True,
) -> Path:
    """Resolve ``(library_root, doc_id)`` to the canonical PDF path.

    Primary resolution uses ``ArtifactResolver.source_pdf(doc_id)``. If that
    file does not exist, we fall back to the filename recorded in the
    ``LibraryStore`` so endpoints work for documents imported before the
    canonical ``source.pdf`` layout was enforced.

    Raises:
        InvalidPathError: If ``library_root`` or ``doc_id`` is unsafe.
        DocumentNotFoundError: If ``must_exist`` is True and no PDF is found.
    """
    root = resolve_library_root(library_root)
    validate_doc_id(doc_id)

    resolver = ArtifactResolver(root)
    try:
        canonical = resolver.source_pdf(doc_id)
    except InvalidDocIdError as exc:
        raise InvalidPathError(str(exc)) from exc

    canonical_resolved = canonical.resolve()
    _ensure_inside_root(canonical_resolved, root)
    if canonical_resolved.is_file():
        return canonical_resolved

    # Fallback: the imported file may still be stored under its original name.
    stored = _resolve_stored_pdf(root, doc_id)
    if stored is not None and (not must_exist or stored.is_file()):
        return stored

    if must_exist:
        raise DocumentNotFoundError(f"PDF not found: {doc_id}")
    return canonical_resolved


def _resolve_stored_pdf(root: Path, doc_id: str) -> Path | None:
    """Look up a document's on-disk file via ``LibraryStore``.

    Returns ``None`` when the store is unavailable or the document is not
    registered.
    """
    try:
        from ..core.library import LibraryStore

        store = LibraryStore.get(str(root))
        stored = store.resolve_file(doc_id)
    except Exception:  # noqa: BLE001 - best-effort fallback
        return None
    if not stored:
        return None
    stored_path = Path(stored).resolve()
    try:
        stored_path.relative_to(root.resolve())
    except ValueError:
        return None
    return stored_path


