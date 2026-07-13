"""Single-DB migration: index/*.db -> .mbforge/library.db.

Phase 4 of the path-migration plan. The pre-Phase-4 layout had two
SQLite databases per library:

* ``{root}/index/knowledge_base.db`` — KB_SCHEMA (figure_labels,
  coref_predictions, ingest_queue, ingest_logs, semantic_cache,
  sections)
* ``{root}/index/molecules.db`` — MOL_SCHEMA + EVIDENCE_SCHEMA + MOL_FTS
  (molecules, molecule_images, molecule_relations,
  molecule_detections, text_molecule_links, evidence, FTS5)

This module consolidates them into a single
``{root}/.mbforge/library.db`` that holds every table from both legacy
databases.

Migration flow (idempotent and failsafe):

1. **Detect** — check whether the migration is needed.
   * Already migrated: ``.mbforge/library.db`` exists; nothing to do.
   * Nothing to migrate: ``index/knowledge_base.db`` and
     ``index/molecules.db`` are both missing; nothing to do.
   * Otherwise: migration required.

2. **Build** — create a *temp* database in ``.mbforge/library.db.tmp``
   with the unified schema, then ``INSERT INTO new SELECT FROM old``
   for every table that exists in the source. Tables missing from the
   source are simply skipped (the unified schema already created them
   empty).

3. **Validate** — before swapping, check that the temp db's row counts
   match the source for every table that was migrated. A mismatch
   raises ``MigrationValidationError`` and the temp file is deleted;
   the legacy databases are never touched.

4. **Archive** — on success, the legacy ``index/`` directory is moved
   to ``.mbforge/migrations/{ISO-timestamp}/index/`` and a
   ``MIGRATION.md`` marker is written. The unified
   ``.mbforge/library.db`` is renamed from ``.tmp`` to its final
   path. The library's runtime path is now the unified database.

If any step fails, the temp database is deleted and the legacy
databases are never touched — the operator can re-run the migration.

CLI:

    uv run python -m mbforge.migrate-library <library_root> [--dry-run]

``--dry-run`` prints the would-be actions (which tables would be
copied, row counts) without touching any files.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..utils.logger import get_logger
from .database import _KB_SCHEMA, DatabaseManager
from .layout import LibraryLayout
from .library import _LIBRARY_SCHEMA

logger = get_logger("mbforge.core.migration")

# Single source of truth for the KB schema. Keeping this alias preserves
# backward compatibility for tests that build synthetic legacy databases.
_KB_SCHEMA_DDL = _KB_SCHEMA

# Tables the migration is allowed to copy. Used to prevent accidental
# SQL injection via the table-name placeholders in ``_copy_table``.
_VALID_TABLES: frozenset[str] = frozenset(
    {
        "figure_labels",
        "coref_predictions",
        "ingest_queue",
        "ingest_logs",
        "semantic_cache",
        "sections",
        "molecules",
        "molecule_images",
        "molecule_relations",
        "molecule_detections",
        "text_molecule_links",
        "evidence",
        "mol_search",
        "schema_version",
        "documents",
        "collections",
        "collection_members",
        "tasks",
    }
)


class MigrationError(RuntimeError):
    """Base class for all migration errors."""


class AlreadyMigratedError(MigrationError):
    """The library is already on the unified layout."""


class NothingToMigrateError(MigrationError):
    """Neither legacy database exists; nothing to migrate."""


class MigrationValidationError(MigrationError):
    """Row-count mismatch after the temp db was built."""


@dataclass
class MigrationReport:
    """Summary of one migration run."""

    library_root: Path
    dry_run: bool = False
    skipped: bool = False
    skip_reason: str = ""
    # For each migrated table: (rows_copied, source_path, target_path).
    tables: dict[str, tuple[int, Path, Path]] = field(default_factory=dict)
    archive_dir: Path | None = None
    unified_db: Path | None = None
    duration_ms: int = 0

    def summary_lines(self) -> list[str]:
        if self.skipped:
            return [f"SKIPPED: {self.skip_reason}"]
        lines = [f"Migration {'(dry-run) ' if self.dry_run else ''}complete:"]
        for table, (rows, src, dst) in sorted(self.tables.items()):
            lines.append(f"  - {table}: {rows} rows  ({src.name} -> {dst.name})")
        if self.unified_db:
            lines.append(f"Unified DB: {self.unified_db}")
        if self.archive_dir:
            lines.append(f"Archived legacy: {self.archive_dir}")
        lines.append(f"Duration: {self.duration_ms} ms")
        return lines


# Per-table SQL for the unified database. The order matters: tables
# with FOREIGN KEYs must come after the tables they reference. We
# declare schema in ``DatabaseManager.molecule_schema()`` (single source
# of truth) and the migration just runs that.
def _unified_schema() -> str:
    """Return the SQL DDL for the unified library.db.

    Combines LibraryStore schema (documents, collections,
    collection_members, tasks), molecule schema (molecules + evidence +
    FTS) and KB schema (figure_labels + coref_predictions + ingest +
    semantic_cache + sections).
    """
    return (
        _LIBRARY_SCHEMA
        + "\n"
        + DatabaseManager.molecule_schema()
        + "\n"
        + _KB_SCHEMA_DDL
    )


# Map of table -> legacy source database files. Tables not present in any
# source file are simply skipped (the unified schema already created them
# empty).
_LEGACY_TABLE_SOURCES: dict[str, tuple[Path | None, Path | None, Path | None]] = {}


def _build_legacy_table_sources(
    layout: LibraryLayout,
) -> dict[str, tuple[Path | None, Path | None, Path | None]]:
    """Map of table name -> (legacy_kb_path, legacy_mol_path, legacy_lib_path).

    Any legacy file may be missing. The migration only copies a table if
    its source database exists and the table is present in that source.
    Pre-Phase-4 libraries may also keep LibraryStore tables in the root
    ``library.db`` file, so that is included as a third source.
    """
    # Hand-curated: the molecule-side tables live in molecules.db; the
    # KB-side tables live in knowledge_base.db; LibraryStore tables live
    # in the root library.db. Adding a new table to any schema means
    # updating this map.
    mol_tables = {
        "molecules",
        "molecule_images",
        "molecule_relations",
        "molecule_detections",
        "text_molecule_links",
        "evidence",
        "mol_search",
        "schema_version",
    }
    kb_tables = {
        "figure_labels",
        "coref_predictions",
        "ingest_queue",
        "ingest_logs",
        "semantic_cache",
        "sections",
    }
    lib_tables = {
        "documents",
        "collections",
        "collection_members",
        "tasks",
    }
    legacy_lib_db = layout.library_root / "library.db"
    sources: dict[str, tuple[Path | None, Path | None, Path | None]] = {}
    for t in mol_tables:
        sources[t] = (None, layout.legacy_index_dir / "molecules.db", None)
    for t in kb_tables:
        sources[t] = (layout.legacy_index_dir / "knowledge_base.db", None, None)
    for t in lib_tables:
        sources[t] = (None, None, legacy_lib_db)
    return sources


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (table,),
    )
    return cur.fetchone() is not None


def _copy_table(
    src_conn: sqlite3.Connection,
    dst_conn: sqlite3.Connection,
    table: str,
) -> int:
    """Copy all rows from ``src_conn[table]`` to ``dst_conn[table]``.

    Returns the number of rows copied. Raises on the first SQL error.
    The table name is validated against a whitelist before interpolation
    to avoid SQL injection from user-controlled legacy database layouts.
    """
    if table not in _VALID_TABLES:
        raise ValueError(f"Refusing to copy unrecognised table: {table}")
    rows = src_conn.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        return 0
    placeholders = ",".join("?" * len(rows[0]))
    dst_conn.executemany(
        f"INSERT OR IGNORE INTO {table} VALUES ({placeholders})",
        rows,
    )
    return len(rows)


def detect_state(library_root: str | Path) -> dict[str, Any]:
    """Return a dict describing the current migration state of a library.

    Useful for ``--dry-run`` and for tests.
    """
    layout = LibraryLayout(library_root)
    layout.ensure_metadata_dir()  # safe: mkdir is a no-op on existing
    state: dict[str, Any] = {
        "unified_db": str(layout.database_path),
        "unified_db_exists": layout.database_path.exists(),
        "kb_db": str(layout.legacy_index_dir / "knowledge_base.db"),
        "kb_db_exists": (layout.legacy_index_dir / "knowledge_base.db").exists(),
        "mol_db": str(layout.legacy_index_dir / "molecules.db"),
        "mol_db_exists": (layout.legacy_index_dir / "molecules.db").exists(),
    }
    if state["unified_db_exists"]:
        state["status"] = "already_migrated"
    elif state["kb_db_exists"] or state["mol_db_exists"]:
        state["status"] = "needs_migration"
    else:
        state["status"] = "nothing_to_migrate"
    return state


def migrate_library(
    library_root: str | Path, *, dry_run: bool = False
) -> MigrationReport:
    """Run the single-DB migration for ``library_root``.

    See module docstring for the full flow. Returns a ``MigrationReport``.
    Raises ``MigrationError`` subclasses on hard failure (already
    migrated, nothing to migrate, validation mismatch). A
    ``RuntimeError`` is raised on filesystem errors (e.g. permission).
    """
    started = datetime.now()
    layout = LibraryLayout(library_root)
    report = MigrationReport(library_root=Path(library_root), dry_run=dry_run)
    sources = _build_legacy_table_sources(layout)

    # 1. Detect ---------------------------------------------------------
    state = detect_state(library_root)
    if state["status"] == "already_migrated":
        report.skipped = True
        report.skip_reason = (
            f"unified database already exists at {layout.database_path}"
        )
        logger.info("Skip: %s", report.skip_reason)
        return report
    if state["status"] == "nothing_to_migrate":
        report.skipped = True
        report.skip_reason = f"no legacy databases under {layout.legacy_index_dir}"
        logger.info("Skip: %s", report.skip_reason)
        return report

    # 2. Plan -----------------------------------------------------------
    plan: list[tuple[str, Path]] = []
    for table, (kb, mol, lib) in sources.items():
        # Prefer the source that actually exists; if multiple exist,
        # prefer the one whose schema is the table's home (see
        # ``_build_legacy_table_sources``). Sources may be missing
        # (None) for cross-schema tables we never migrate.
        if kb is not None and kb.exists():
            plan.append((table, kb))
        elif mol is not None and mol.exists():
            plan.append((table, mol))
        elif lib is not None and lib.exists():
            plan.append((table, lib))
    if not plan:
        report.skipped = True
        report.skip_reason = "no tables to migrate"
        return report

    # 3. Build (or simulate) -------------------------------------------
    tmp_path = layout.database_path.with_suffix(".db.tmp")
    final_path = layout.database_path

    if dry_run:
        # Open each source, count rows, return a synthetic report.
        for table, src in plan:
            try:
                conn = sqlite3.connect(str(src))
                n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                conn.close()
            except sqlite3.OperationalError:
                # Table missing in this source — skip.
                continue
            report.tables[table] = (n, src, final_path)
        report.duration_ms = int((datetime.now() - started).total_seconds() * 1000)
        logger.info("Dry-run: would migrate %d tables", len(report.tables))
        return report

    # 3a. Build temp db.
    layout.ensure_metadata_dir()
    if tmp_path.exists():
        tmp_path.unlink()
    dst = sqlite3.connect(str(tmp_path))
    try:
        dst.executescript(_unified_schema())
        # Open each source, copy each table.
        open_srcs: dict[Path, sqlite3.Connection] = {}
        try:
            for table, src in plan:
                if src not in open_srcs:
                    open_srcs[src] = sqlite3.connect(str(src))
                src_conn = open_srcs[src]
                if not _table_exists(src_conn, table):
                    logger.info("Skip missing table %s in %s", table, src)
                    continue
                n = _copy_table(src_conn, dst, table)
                report.tables[table] = (n, src, final_path)
                logger.info("Copied %d rows from %s.%s", n, src.name, table)
            dst.commit()
        finally:
            for c in open_srcs.values():
                c.close()

        # 4. Validate ----------------------------------------------------
        for table, (n_expected, _src, _dst) in report.tables.items():
            n_actual = dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if n_actual != n_expected:
                raise MigrationValidationError(
                    f"Row count mismatch for {table}: expected {n_expected}, "
                    f"got {n_actual}"
                )

        dst.close()
    except Exception:
        dst.close()
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    # 5. Archive + atomic swap ----------------------------------------
    archive_dir = layout.migration_archive_dir()
    archive_dir.mkdir(parents=True, exist_ok=True)
    legacy_index = layout.legacy_index_dir
    archived_index = archive_dir / "index"
    if legacy_index.exists():
        shutil.move(str(legacy_index), str(archived_index))
        # The archived layout keeps WAL/SHM siblings too, in case the
        # operator wants to recover.
        # SQLite WAL/SHM sidecars live next to the db file. For an
        # index/ directory (no suffix) the siblings are literally
        # ``index-wal`` / ``index-shm`` (SQLite's behavior for the
        # implicit connection db). We use string concatenation rather
        # than ``Path.with_suffix`` because the latter rejects suffixes
        # that do not start with ``.``.
        for sibling_name in (
            str(legacy_index) + "-wal",
            str(legacy_index) + "-shm",
        ):
            sibling = Path(sibling_name)
            if sibling.exists():
                shutil.move(str(sibling), str(archived_index / sibling.name))
    # Archive the legacy root library.db if it exists.
    legacy_lib_db = layout.library_root / "library.db"
    if legacy_lib_db.exists():
        shutil.move(str(legacy_lib_db), str(archive_dir / "library.db"))
        for suffix in ("-wal", "-shm"):
            sibling = Path(str(legacy_lib_db) + suffix)
            if sibling.exists():
                shutil.move(
                    str(sibling), str(archive_dir / (legacy_lib_db.name + suffix))
                )
    # Move the temp db into place.
    shutil.move(str(tmp_path), str(final_path))
    # Write a migration marker.
    _write_migration_marker(archive_dir, report.tables)
    report.unified_db = final_path
    report.archive_dir = archive_dir

    report.duration_ms = int((datetime.now() - started).total_seconds() * 1000)
    logger.info(
        "Migration complete: %d tables, %d ms, archive=%s",
        len(report.tables),
        report.duration_ms,
        archive_dir,
    )
    return report


def _write_migration_marker(
    archive_dir: Path,
    tables: dict[str, tuple[int, Path, Path]],
) -> None:
    """Write a MIGRATION.md marker into the archive directory.

    Future readers of the archived layout can see what was migrated
    and when.
    """
    marker = archive_dir / "MIGRATION.md"
    lines = [
        "# MBForge single-DB migration",
        "",
        f"Archived at: {datetime.now().isoformat(timespec='seconds')}",
        "",
        f"Tables migrated ({len(tables)}):",
        "",
    ]
    for table, (rows, src, _dst) in sorted(tables.items()):
        lines.append(f"- **{table}**: {rows} rows (from `{src.name}`)")
    lines += [
        "",
        "Archived files:",
        "- `index/knowledge_base.db` and `index/molecules.db`",
        "- `library.db` (root LibraryStore + molecule tables, if present)",
        "",
        "Recovery: move `index/` and `library.db` back to the library root",
        "and delete the unified `.mbforge/library.db`. The legacy layout",
        "will be functional again.",
    ]
    marker.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``python -m mbforge.migrate-library``."""
    parser = argparse.ArgumentParser(
        prog="python -m mbforge.migrate-library",
        description=(
            "Migrate a library from the legacy layout "
            "({root}/library.db + {root}/index/*.db) to the unified "
            "single-database layout ({root}/.mbforge/library.db)."
        ),
    )
    parser.add_argument(
        "library_root",
        type=Path,
        help="Path to the library root (the directory containing index/, storage/, etc.)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the migration plan without touching any files.",
    )
    args = parser.parse_args(argv)

    try:
        report = migrate_library(args.library_root, dry_run=args.dry_run)
    except MigrationError as exc:
        print(f"Migration FAILED: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Migration ERROR: {exc}", file=sys.stderr)
        return 2

    for line in report.summary_lines():
        print(line)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
