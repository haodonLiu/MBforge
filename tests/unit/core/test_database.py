"""Tests for core database manager."""

import sqlite3
from pathlib import Path

from mbforge.core.database import DatabaseManager


class TestDatabaseManager:
    def test_initialize_creates_files(self, tmp_path):
        db = DatabaseManager(str(tmp_path))
        db.initialize()
        assert db.kb_path.exists()
        assert db.mol_path.exists()

    def test_kb_tables_exist(self, tmp_path):
        db = DatabaseManager(str(tmp_path))
        db.initialize()
        with db.kb_conn() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {t["name"] for t in tables}
        assert "figure_labels" in table_names
        assert "coref_predictions" in table_names
        assert "ingest_queue" in table_names
        assert "semantic_cache" in table_names

    def test_mol_tables_exist(self, tmp_path):
        db = DatabaseManager(str(tmp_path))
        db.initialize()
        with db.mol_conn() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {t["name"] for t in tables}
        assert "molecules" in table_names
        assert "molecule_images" in table_names
        assert "molecule_relations" in table_names
        assert "mol_search" in table_names

    def test_double_initialize_is_idempotent(self, tmp_path):
        db = DatabaseManager(str(tmp_path))
        db.initialize()
        db.initialize()  # should not raise

    def test_kb_conn_rollback_on_error(self, tmp_path):
        db = DatabaseManager(str(tmp_path))
        db.initialize()
        try:
            with db.kb_conn() as conn:
                conn.execute("INSERT INTO ingest_queue (id, file_path) VALUES ('x', 'y')")
                raise ValueError("boom")
        except ValueError:
            pass
        with db.kb_conn() as conn:
            row = conn.execute("SELECT * FROM ingest_queue WHERE id = 'x'").fetchone()
            assert row is None  # rolled back

    def test_mol_conn_commits(self, tmp_path):
        db = DatabaseManager(str(tmp_path))
        db.initialize()
        with db.mol_conn() as conn:
            conn.execute(
                "INSERT INTO molecules (mol_id, smiles) VALUES (?, ?)",
                ("mol_1", "CCO"),
            )
        with db.mol_conn() as conn:
            row = conn.execute("SELECT * FROM molecules WHERE mol_id = 'mol_1'").fetchone()
            assert row is not None
            assert row["smiles"] == "CCO"

    def test_schema_version_set(self, tmp_path):
        db = DatabaseManager(str(tmp_path))
        db.initialize()
        with db.mol_conn() as conn:
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            assert row is not None
            assert row["version"] == 2
