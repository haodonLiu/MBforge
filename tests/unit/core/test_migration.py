"""Tests for the single-DB migration module.

Each test uses a fresh ``tmp_path`` (provided by pytest) and never
touches the user's real library. The migrations it runs operate on
synthetic legacy databases built from the same schema strings the
real code uses, so a regression in either the schema or the migration
logic is caught here.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from mbforge.core import migration as mig


def _create_legacy_kb_db(path: Path) -> None:
    """Create a synthetic knowledge_base.db at ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(mig._KB_SCHEMA_DDL)
        conn.executemany(
            "INSERT INTO figure_labels (doc_id, page, label_bbox, label_text, ocr_conf, image_path) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("doc-a", 1, "10,20,30,40", "Mol-1", 0.9, "img1.png"),
                ("doc-a", 2, "11,21,31,41", "Mol-2", 0.8, "img2.png"),
                ("doc-b", 1, "12,22,32,42", "Mol-3", 0.7, "img3.png"),
            ],
        )
        conn.executemany(
            "INSERT INTO coref_predictions (doc_id, page, mol_smiles, mol_bbox, mol_conf, label_text, label_bbox, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("doc-a", 1, "CCO", "1,2,3,4", 0.9, "Mol-1", "10,20,30,40", 0.85),
            ],
        )
        conn.executemany(
            "INSERT INTO sections (doc_id, section_index, title, level) VALUES (?, ?, ?, ?)",
            [
                ("doc-a", 1, "Intro", 1),
                ("doc-a", 2, "Methods", 1),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _create_legacy_mol_db(path: Path) -> None:
    """Create a synthetic molecules.db at ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(mig.DatabaseManager.molecule_schema())
        # Insert a few canonical molecules
        conn.executemany(
            "INSERT INTO molecules (mol_id, smiles, esmiles, name) VALUES (?, ?, ?, ?)",
            [
                ("CCO", "CCO", "CCO", "ethanol"),
                ("CCN", "CCN", "CCN", "ethylamine"),
            ],
        )
        conn.executemany(
            "INSERT INTO evidence (canonical_smiles, doc_id, page, kind, confidence) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                ("CCO", "doc-a", 1, "figure", 0.9),
                ("CCO", "doc-a", 2, "text", 0.7),
                ("CCN", "doc-b", 1, "figure", 0.85),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _create_legacy_library_db(path: Path) -> None:
    """Create a synthetic root library.db with LibraryStore tables."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(mig._LIBRARY_SCHEMA)
        conn.executemany(
            "INSERT INTO documents (doc_id, title, file_name, storage_path, md5) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                ("doc-1", "Paper One", "one.pdf", "storage/doc-1/source.pdf", "a"),
                ("doc-2", "Paper Two", "two.pdf", "storage/doc-2/source.pdf", "b"),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def test_detect_state_already_migrated(tmp_path: Path) -> None:
    """If unified library.db already exists, detect_state says so."""
    layout = mig.LibraryLayout(tmp_path)
    layout.ensure_metadata_dir()
    layout.database_path.touch()
    state = mig.detect_state(tmp_path)
    assert state["status"] == "already_migrated"
    assert state["unified_db_exists"] is True


def test_detect_state_nothing_to_migrate(tmp_path: Path) -> None:
    """If no legacy DBs exist, detect_state says nothing_to_migrate."""
    state = mig.detect_state(tmp_path)
    assert state["status"] == "nothing_to_migrate"


def test_detect_state_needs_migration(tmp_path: Path) -> None:
    """If at least one legacy DB exists, detect_state says needs_migration."""
    _create_legacy_kb_db(tmp_path / "index" / "knowledge_base.db")
    state = mig.detect_state(tmp_path)
    assert state["status"] == "needs_migration"


def test_migrate_dry_run_leaves_files_untouched(tmp_path: Path) -> None:
    """``--dry-run`` must not touch any files on disk."""
    kb_path = tmp_path / "index" / "knowledge_base.db"
    mol_path = tmp_path / "index" / "molecules.db"
    _create_legacy_kb_db(kb_path)
    _create_legacy_mol_db(mol_path)
    report = mig.migrate_library(tmp_path, dry_run=True)
    assert report.dry_run is True
    assert report.skipped is False
    # All non-empty tables should be reported
    assert "molecules" in report.tables
    assert "figure_labels" in report.tables
    # Files unchanged
    assert kb_path.exists()
    assert mol_path.exists()
    assert not (mig.LibraryLayout(tmp_path).database_path).exists()


def test_migrate_runs_and_unifies(tmp_path: Path) -> None:
    """A real migration moves data into the unified db and archives legacy."""
    _create_legacy_kb_db(tmp_path / "index" / "knowledge_base.db")
    _create_legacy_mol_db(tmp_path / "index" / "molecules.db")
    report = mig.migrate_library(tmp_path)
    assert report.skipped is False
    assert report.unified_db is not None
    assert report.archive_dir is not None
    # Source legacy files have been moved into the archive
    archive_index = report.archive_dir / "index"
    assert (archive_index / "knowledge_base.db").exists()
    assert (archive_index / "molecules.db").exists()
    # Unified db exists and contains the rows
    unified = report.unified_db
    conn = sqlite3.connect(str(unified))
    try:
        n_fl = conn.execute("SELECT COUNT(*) FROM figure_labels").fetchone()[0]
        n_mol = conn.execute("SELECT COUNT(*) FROM molecules").fetchone()[0]
        n_ev = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    finally:
        conn.close()
    assert n_fl == 3
    assert n_mol == 2
    assert n_ev == 3
    # MIGRATION.md marker exists
    assert (report.archive_dir / "MIGRATION.md").exists()


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    """Running migrate twice: the second run skips (already migrated)."""
    _create_legacy_kb_db(tmp_path / "index" / "knowledge_base.db")
    _create_legacy_mol_db(tmp_path / "index" / "molecules.db")
    first = mig.migrate_library(tmp_path)
    assert not first.skipped
    second = mig.migrate_library(tmp_path)
    assert second.skipped is True
    assert "already" in second.skip_reason.lower()


def test_migrate_handles_partial_legacy(tmp_path: Path) -> None:
    """If only the KB db exists (no molecules.db), migrate still works."""
    _create_legacy_kb_db(tmp_path / "index" / "knowledge_base.db")
    # no molecules.db
    report = mig.migrate_library(tmp_path)
    assert not report.skipped
    assert "molecules" not in report.tables  # table missing in source
    assert "figure_labels" in report.tables


def test_migrate_includes_root_library_db(tmp_path: Path) -> None:
    """A legacy root library.db is merged into the unified db."""
    _create_legacy_kb_db(tmp_path / "index" / "knowledge_base.db")
    _create_legacy_mol_db(tmp_path / "index" / "molecules.db")
    _create_legacy_library_db(tmp_path / "library.db")
    report = mig.migrate_library(tmp_path)
    assert not report.skipped
    assert report.archive_dir is not None
    assert (report.archive_dir / "library.db").exists()
    # Unified db has both KB/molecule rows and LibraryStore rows.
    unified = report.unified_db
    conn = sqlite3.connect(str(unified))
    try:
        n_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        n_mol = conn.execute("SELECT COUNT(*) FROM molecules").fetchone()[0]
        n_fl = conn.execute("SELECT COUNT(*) FROM figure_labels").fetchone()[0]
    finally:
        conn.close()
    assert n_docs == 2
    assert n_mol == 2
    assert n_fl == 3


def test_migrate_validation_failsafe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If row count validation fails, the temp db is deleted and legacy is kept.

    This is tested by monkeypatching ``_copy_table`` to mis-report the
    number of rows actually inserted (return more than the SQL
    executed). The validator should catch the mismatch and clean up.
    """
    _create_legacy_kb_db(tmp_path / "index" / "knowledge_base.db")
    _create_legacy_mol_db(tmp_path / "index" / "molecules.db")

    real_copy = mig._copy_table
    call_count = {"n": 0}

    def fake_copy(src_conn, dst_conn, table):
        # Real copy works, but report an inflated row count.
        actual = real_copy(src_conn, dst_conn, table)
        call_count["n"] += 1
        return actual + 100  # lie about how many rows we copied

    monkeypatch.setattr(mig, "_copy_table", fake_copy)
    with pytest.raises(mig.MigrationValidationError):
        mig.migrate_library(tmp_path)

    # Temp db must be deleted; legacy dbs must still be present.
    assert not (
        mig.LibraryLayout(tmp_path).database_path.with_suffix(".db.tmp")
    ).exists()
    assert not (mig.LibraryLayout(tmp_path).database_path).exists()
    assert (tmp_path / "index" / "knowledge_base.db").exists()
    assert (tmp_path / "index" / "molecules.db").exists()


def test_migrate_nothing_to_migrate(tmp_path: Path) -> None:
    """Empty library: skip with informative reason."""
    report = mig.migrate_library(tmp_path)
    assert report.skipped is True
    assert (
        "no legacy" in report.skip_reason.lower()
        or "nothing" in report.skip_reason.lower()
    )


def test_main_dry_run_via_argv(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """CLI: ``python -m mbforge.migrate-library <root> --dry-run`` exits 0."""
    _create_legacy_kb_db(tmp_path / "index" / "knowledge_base.db")
    rc = mig.main([str(tmp_path), "--dry-run"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "figure_labels" in captured.out


def test_main_already_migrated_via_argv(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """CLI: already-migrated exit 0 with SKIPPED message."""
    layout = mig.LibraryLayout(tmp_path)
    layout.ensure_metadata_dir()
    layout.database_path.touch()
    rc = mig.main([str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "SKIPPED" in captured.out


def test_copy_table_rejects_unrecognised_table(tmp_path: Path) -> None:
    """_copy_table must refuse to interpolate arbitrary table names."""
    src = tmp_path / "src.db"
    dst = tmp_path / "dst.db"
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dst))
    try:
        src_conn.execute("CREATE TABLE bad (id INTEGER)")
        with pytest.raises(ValueError, match="Refusing to copy"):
            mig._copy_table(src_conn, dst_conn, "bad; DROP TABLE documents")
    finally:
        src_conn.close()
        dst_conn.close()


def test_kb_schema_ddl_matches_database_source() -> None:
    """The migration module must reuse the DatabaseManager KB schema."""
    from mbforge.core.database import _KB_SCHEMA as DB_KB_SCHEMA

    assert mig._KB_SCHEMA_DDL is DB_KB_SCHEMA
