"""Single authority for resolving artifact paths under library_root.

All file reads / writes that touch a path under the library root go through
``ArtifactResolver`` so the storage layout is defined in one place and path
traversal attacks are rejected at a single chokepoint.

Layout (under ``{library_root}``):

* ``storage/{doc_id}/source.pdf``     — original imported PDF bytes
* ``storage/{doc_id}/reorganized.md`` — LLM-reorganized markdown
* ``storage/{doc_id}/indexed.md``     — PageIndex-indexed markdown
* ``storage/{doc_id}/report.json``    — pipeline report
* ``storage/{doc_id}/pages/page_{n:04d}.txt``  — per-page OCR text (1-based)
* ``storage/{doc_id}/crops/{filename}``   — molecule crop images

The legacy layout ``.mbforge/crops/{doc_id}/`` is also accepted for reads
(so existing libraries keep working before the migration script runs), but
new writes go to the canonical location.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..utils.helpers import PathTraversalError  # noqa: F401 — re-export

# Safe doc_id: letters, digits, underscore, hyphen. The same regex is used
# by routers/library.py; keeping it identical preserves back-compat.
_SAFE_DOC_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


class InvalidDocIdError(ValueError):
    """Raised when ``doc_id`` fails the safety regex."""


class ArtifactResolver:
    """Resolve artifact paths under a library root.

    Stateless: construct freely. The root is stored as a ``Path`` and used
    for all path computations. The class performs no I/O — existence checks
    remain the caller's responsibility (``is_file()``, ``mkdir(...)``).
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    @property
    def library_root(self) -> Path:
        """Return the library root (unresolved; matches input form)."""
        return self._root

    def storage_dir(self, doc_id: str) -> Path:
        """Return ``{root}/storage/{doc_id}`` (canonical storage subdir)."""
        return self._validate_and_join("storage", doc_id)

    def source_pdf(self, doc_id: str) -> Path:
        return self.storage_dir(doc_id) / "source.pdf"

    def reorganized_md(self, doc_id: str) -> Path:
        return self.storage_dir(doc_id) / "reorganized.md"

    def indexed_md(self, doc_id: str) -> Path:
        return self.storage_dir(doc_id) / "indexed.md"

    def report_json(self, doc_id: str) -> Path:
        return self.storage_dir(doc_id) / "report.json"

    def pages_dir(self, doc_id: str) -> Path:
        return self.storage_dir(doc_id) / "pages"

    def page_text(self, doc_id: str, page: int) -> Path:
        if page < 1:
            raise ValueError(f"page must be >= 1, got {page}")
        return self.pages_dir(doc_id) / f"page_{int(page):04d}.txt"

    def crops_dir(self, doc_id: str) -> Path:
        return self.storage_dir(doc_id) / "crops"

    def crop(self, doc_id: str, relpath: str) -> Path:
        """Resolve a crop filename to a path under ``storage/{doc_id}/crops/``.

        ``relpath`` is a single filename (``"page_0003_mol_0002.png"``); it must
        not contain path separators. The resolved path is verified to live
        inside the crops directory.
        """
        if not relpath or "/" in relpath or "\\" in relpath or relpath.startswith(".."):
            raise PathTraversalError(f"invalid crop relpath: {relpath!r}")
        target = (self.crops_dir(doc_id) / relpath).resolve()
        try:
            target.relative_to(self.crops_dir(doc_id).resolve())
        except ValueError as exc:
            raise PathTraversalError(f"crop path escapes crops dir: {relpath}") from exc
        return target

    def legacy_crop(self, doc_id: str, relpath: str) -> Path:
        """Resolve a crop under the legacy ``.mbforge/crops/{doc_id}/`` layout.

        Used for read-only back-compat with libraries created before the
        2026-07-10 storage unification. New writes go through :meth:`crop`.
        """
        legacy = (self._root / ".mbforge" / "crops" / doc_id / relpath).resolve()
        legacy_root = (self._root / ".mbforge" / "crops" / doc_id).resolve()
        try:
            legacy.relative_to(legacy_root)
        except ValueError as exc:
            raise PathTraversalError(
                f"crop path escapes legacy crops dir: {relpath}"
            ) from exc
        return legacy

    def _validate_and_join(self, *parts: str) -> Path:
        doc_id = parts[-1]
        if not doc_id or not _SAFE_DOC_ID_RE.match(doc_id):
            raise InvalidDocIdError(f"invalid doc_id: {doc_id!r}")
        return self._root.joinpath(*parts)
