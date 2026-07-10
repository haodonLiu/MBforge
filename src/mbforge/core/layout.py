"""LibraryLayout — single authority for library-level paths.

Mirrors the role of ``ArtifactResolver`` (which owns document-level paths
under ``storage/{doc_id}/``) for the library-level layout: the metadata
dir, the unified database path, the OpenKB / PageIndex index, the
user-editable notes dir, and the migration archive dir.

Layout (under ``{library_root}``):

* ``.mbforge/``                   — internal metadata root (this class's
  ``metadata_dir``); never user-edited.
* ``.mbforge/library.db``         — unified business + molecule database
  (post-Phase-4 migration). Pre-Phase-4 libraries still have two
  legacy databases under ``index/``; ``DatabaseManager`` and
  ``LibraryStore`` fall back to those until the migration runs.
* ``.mbforge/openkb/``            — OpenKB + PageIndex + dense-rerank cache.
* ``notes/``                      — user-editable notes (Phase 5).
* ``.mbforge/migrations/{ts}/``   — archive directory for superseded
  layout versions.

No module is allowed to inline-construct these paths. After Phase 2
lands, ``rg ' / "index"| / "\\.mbforge"' src/mbforge`` should match only
``LibraryLayout`` itself, ``ArtifactResolver`` (where the legacy crop
fallback lives), the migration modules, and their tests.

See ``docs/adr/0001-canonical-library-layout.md`` §2 + §3 for the
authoritative layout decision.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


class LibraryLayout:
    """Resolve library-level paths for a single library.

    Stateless: constructing multiple instances for the same root is
    cheap and the resolver never touches the filesystem in its
    accessors. Use the ``ensure_*`` methods to create directories.
    """

    def __init__(self, library_root: str | Path) -> None:
        self._root = Path(library_root)

    @property
    def library_root(self) -> Path:
        """Return the library root (unresolved; matches the input form)."""
        return self._root

    # -- metadata root -------------------------------------------------

    @property
    def metadata_dir(self) -> Path:
        """``{root}/.mbforge/`` — internal metadata root.

        Users do not edit this directly. Library-level bookkeeping
        (unified database, OpenKB index, migration archive) lives here.
        """
        return self._root / ".mbforge"

    @property
    def legacy_index_dir(self) -> Path:
        """``{root}/index/`` — pre-Phase-4 two-database layout.

        Used by ``DatabaseManager`` until the Phase 4 single-DB
        migration runs. After that, ``DatabaseManager`` should be
        deleted entirely in favor of writing to ``database_path``
        (the unified ``{root}/.mbforge/library.db``).
        """
        return self._root / "index"

    @property
    def database_path(self) -> Path:
        """``{root}/.mbforge/library.db`` — unified business + molecule db.

        This is the canonical target after the Phase 4 single-DB
        migration. Until that migration runs, ``DatabaseManager`` and
        ``LibraryStore`` still find the legacy two-db layout under
        ``index/`` and the two can coexist (the legacy path is a
        fallback).
        """
        return self.metadata_dir / "library.db"

    # -- OpenKB / PageIndex ---------------------------------------------

    @property
    def openkb_dir(self) -> Path:
        """``{root}/.mbforge/openkb/`` — OpenKB + PageIndex + dense-rerank cache.

        The OpenKB package itself is a third-party dependency; this
        directory is just the storage backend it points at.
        """
        return self.metadata_dir / "openkb"

    def openkb_wiki_dir(self) -> Path:
        """``{root}/.mbforge/openkb/wiki/`` — wiki markdown cache."""
        return self.openkb_dir / "wiki"

    def openkb_doc_trees_path(self) -> Path:
        """``{root}/.mbforge/openkb/doc_trees.json`` — PageIndex tree cache."""
        return self.openkb_dir / "doc_trees.json"

    # -- user-editable notes (Phase 5) ----------------------------------

    @property
    def notes_dir(self) -> Path:
        """``{root}/notes/`` — user-editable notes (Phase 5 work).

        This is the *only* library-level path users are expected to
        hand-edit or back up themselves. Everything else under
        ``.mbforge/`` is internal state.
        """
        return self._root / "notes"

    # -- migration archive (Phase 4 / Phase 6) --------------------------

    @property
    def migration_dir(self) -> Path:
        """``{root}/.mbforge/migrations/`` — archive for superseded layouts.

        Each migration run (e.g. the Phase 4 single-DB consolidation)
        moves the prior layout into a timestamped subdirectory
        ``{migration_dir}/{ISO-timestamp}/`` and writes a
        ``MIGRATION.md`` marker. The archived layout is never
        referenced by the running code after a successful migration.
        """
        return self.metadata_dir / "migrations"

    def migration_archive_dir(self, when: datetime | None = None) -> Path:
        """Return the timestamped archive subdirectory for a migration run.

        ``when`` defaults to ``datetime.now()`` (local time). The
        subdirectory name is the ISO-8601 timestamp in
        ``YYYYMMDDTHHMMSS`` form (filesystem-safe, sortable).
        """
        stamp = (when or datetime.now()).strftime("%Y%m%dT%H%M%S")
        return self.migration_dir / stamp

    # -- directory bootstrap -------------------------------------------

    def ensure_metadata_dir(self) -> Path:
        """Create ``.mbforge/`` if missing and return the path.

        Idempotent: existing directory is left untouched. Callers
        (e.g. ``DatabaseManager.initialize``) are expected to call
        this before any sqlite3 connection is opened.
        """
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        return self.metadata_dir

    def ensure_notes_dir(self) -> Path:
        """Create ``notes/`` if missing and return the path."""
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        return self.notes_dir

    def ensure_openkb_dir(self) -> Path:
        """Create ``.mbforge/openkb/`` if missing and return the path."""
        self.openkb_dir.mkdir(parents=True, exist_ok=True)
        return self.openkb_dir
