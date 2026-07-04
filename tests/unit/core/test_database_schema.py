import sqlite3
from pathlib import Path

from mbforge.core.database import SCHEMA_VERSION, DatabaseManager


def test_molecules_table_has_review_columns(tmp_path: Path) -> None:
    db = DatabaseManager(str(tmp_path))
    db.initialize()
    with db.mol_conn() as conn:
        row = conn.execute(
            "SELECT name FROM pragma_table_info('molecules') WHERE name IN (?, ?, ?)",
            ("canonical_smiles", "reviewed_at", "review_status"),
        ).fetchall()
        names = {r["name"] for r in row}
    assert names == {"canonical_smiles", "reviewed_at", "review_status"}


def test_molecules_migration_from_v2_adds_review_columns(tmp_path: Path) -> None:
    index_dir = tmp_path / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    mol_path = index_dir / "molecules.db"
    conn = sqlite3.connect(str(mol_path))
    try:
        conn.executescript(
            """
            CREATE TABLE molecules (
                mol_id TEXT PRIMARY KEY,
                smiles TEXT NOT NULL,
                esmiles TEXT,
                name TEXT DEFAULT '',
                source_doc TEXT,
                activity REAL,
                activity_type TEXT,
                units TEXT,
                source_type TEXT DEFAULT 'manual',
                status TEXT DEFAULT 'active',
                properties TEXT DEFAULT '{}',
                labels TEXT DEFAULT '[]',
                semantic_tags TEXT DEFAULT '[]',
                notes TEXT DEFAULT '',
                fingerprint BLOB,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE schema_version (version INTEGER NOT NULL);
            INSERT INTO schema_version (version) VALUES (2);
            """
        )
        conn.commit()
    finally:
        conn.close()

    db = DatabaseManager(str(tmp_path))
    db.initialize()
    with db.mol_conn() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(molecules)")}
        version = conn.execute(
            "SELECT version FROM schema_version"
        ).fetchone()["version"]
    assert {"canonical_smiles", "review_status", "reviewed_at"} <= cols
    assert version == SCHEMA_VERSION == 3
