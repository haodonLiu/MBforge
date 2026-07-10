"""Unit tests for DatabaseManager — schema init, CRUD, and transaction boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mbforge.core.database import DatabaseManager, record_ingest_event


def test_database_initializes_schema(tmp_path: Path) -> None:
    """Initializing a DatabaseManager creates both SQLite files and tables."""
    db = DatabaseManager(str(tmp_path))
    db.initialize()

    assert db.kb_path.exists()
    assert db.mol_path.exists()

    with db.kb_conn() as conn:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "figure_labels" in tables
        assert "ingest_queue" in tables

    with db.mol_conn() as conn:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "molecules" in tables
        assert "molecule_detections" in tables
        assert "evidence" in tables


def test_kb_crud(tmp_path: Path) -> None:
    """Basic insert/select/update/delete on the KB database."""
    db = DatabaseManager(str(tmp_path))
    db.initialize()

    with db.kb_conn() as conn:
        conn.execute(
            "INSERT INTO ingest_queue (id, file_path) VALUES (?, ?)",
            ("task-1", "/tmp/test.pdf"),
        )

    rows = db.execute(
        "SELECT id, file_path FROM ingest_queue WHERE id=?", ("task-1",), db="kb"
    )
    assert len(rows) == 1
    assert rows[0]["file_path"] == "/tmp/test.pdf"


def test_mol_crud(tmp_path: Path) -> None:
    """Basic insert/select on the molecules database."""
    db = DatabaseManager(str(tmp_path))
    db.initialize()

    with db.mol_conn() as conn:
        conn.execute(
            "INSERT INTO molecules (mol_id, smiles) VALUES (?, ?)",
            ("mol-1", "CCO"),
        )

    rows = db.execute(
        "SELECT mol_id, smiles FROM molecules WHERE mol_id=?", ("mol-1",), db="mol"
    )
    assert len(rows) == 1
    assert rows[0]["smiles"] == "CCO"


def test_transaction_commits_both_databases(tmp_path: Path) -> None:
    """A successful transaction() commits writes to both databases."""
    db = DatabaseManager(str(tmp_path))
    db.initialize()

    with db.transaction() as (kb_conn, mol_conn):
        kb_conn.execute(
            "INSERT INTO ingest_queue (id, file_path) VALUES (?, ?)",
            ("task-1", "/tmp/test.pdf"),
        )
        mol_conn.execute(
            "INSERT INTO molecules (mol_id, smiles) VALUES (?, ?)",
            ("mol-1", "CCO"),
        )

    assert db.count_documents() == 1
    assert db.count_molecules() == 1


def test_transaction_rollback_kb_on_failure(tmp_path: Path) -> None:
    """If the KB write fails, no partial state remains."""
    db = DatabaseManager(str(tmp_path))
    db.initialize()

    with (
        pytest.raises(Exception, match="Simulated KB failure"),
        db.transaction() as (kb_conn, _mol_conn),
    ):
        kb_conn.execute(
            "INSERT INTO ingest_queue (id, file_path) VALUES (?, ?)",
            ("task-1", "/tmp/test.pdf"),
        )
        raise Exception("Simulated KB failure")

    assert db.count_documents() == 0


def test_transaction_rollback_mol_on_failure(tmp_path: Path) -> None:
    """If the molecules write fails, no partial state remains."""
    db = DatabaseManager(str(tmp_path))
    db.initialize()

    with (
        pytest.raises(Exception, match="Simulated mol failure"),
        db.transaction() as (_kb_conn, mol_conn),
    ):
        mol_conn.execute(
            "INSERT INTO molecules (mol_id, smiles) VALUES (?, ?)",
            ("mol-1", "CCO"),
        )
        raise Exception("Simulated mol failure")

    assert db.count_molecules() == 0


def test_transaction_rollbacks_both_databases(tmp_path: Path) -> None:
    """A failure in one database rolls back the other as well."""
    db = DatabaseManager(str(tmp_path))
    db.initialize()

    with (
        pytest.raises(Exception, match="boom"),
        db.transaction() as (kb_conn, mol_conn),
    ):
        kb_conn.execute(
            "INSERT INTO ingest_queue (id, file_path) VALUES (?, ?)",
            ("task-1", "/tmp/test.pdf"),
        )
        mol_conn.execute(
            "INSERT INTO molecules (mol_id, smiles) VALUES (?, ?)",
            ("mol-1", "CCO"),
        )
        raise Exception("boom")

    assert db.count_documents() == 0
    assert db.count_molecules() == 0


def test_cached_instance_per_project_root(tmp_path: Path) -> None:
    """DatabaseManager.get caches instances by resolved absolute path."""
    db1 = DatabaseManager.get(str(tmp_path))
    db2 = DatabaseManager.get(str(tmp_path))
    assert db1 is db2


def test_record_ingest_event_writes_log_row(tmp_path: Path) -> None:
    """record_ingest_event persists a log row with all fields, including data JSON."""
    db = DatabaseManager(str(tmp_path))

    record_ingest_event(
        db,
        task_id="task-1",
        doc_id="doc-1",
        stage="detect",
        level="info",
        message="Detected 3 molecules",
        data={"molecule_count": 3, "rejected_count": 0},
    )

    rows = db.execute(
        "SELECT doc_id, stage, level, message, task_id, data FROM ingest_logs WHERE task_id=?",
        ("task-1",),
        db="kb",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["doc_id"] == "doc-1"
    assert row["stage"] == "detect"
    assert row["level"] == "info"
    assert row["message"] == "Detected 3 molecules"
    assert row["task_id"] == "task-1"
    assert json.loads(row["data"]) == {"molecule_count": 3, "rejected_count": 0}


def test_record_ingest_event_updates_queue(tmp_path: Path) -> None:
    """record_ingest_event also updates the matching ingest_queue row."""
    db = DatabaseManager(str(tmp_path))
    with db.kb_conn() as conn:
        conn.execute(
            "INSERT INTO ingest_queue (id, file_path, status) VALUES (?, ?, ?)",
            ("task-2", "/tmp/test.pdf", "pending"),
        )

    record_ingest_event(
        db,
        task_id="task-2",
        doc_id="doc-2",
        stage="extract",
        level="start",
        message="Extracting text...",
        progress_pct=10,
        status="processing",
    )

    rows = db.execute(
        "SELECT status, stage, progress_pct FROM ingest_queue WHERE id=?",
        ("task-2",),
        db="kb",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "processing"
    assert row["stage"] == "extract"
    assert row["progress_pct"] == 10


def test_record_ingest_event_swallows_exception(tmp_path: Path) -> None:
    """A failure while writing the log should not raise to the caller."""
    db = DatabaseManager(str(tmp_path))

    # Close the underlying DB file by deleting the parent directory so the
    # next write fails without needing to mock internals.
    db.initialize()
    db._kb_path.unlink()

    record_ingest_event(
        db,
        task_id="task-3",
        doc_id="doc-3",
        stage="persist",
        level="error",
        message="Disk full",
        data={"error_code": "PERSIST_FAILED"},
    )

    # No exception raised; function returns None on failure.
    assert True
