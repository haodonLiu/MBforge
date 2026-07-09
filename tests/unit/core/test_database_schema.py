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
        version = conn.execute("SELECT version FROM schema_version").fetchone()[
            "version"
        ]
    assert {"canonical_smiles", "review_status", "reviewed_at"} <= cols
    assert version == SCHEMA_VERSION == 3


def test_text_molecule_links_table_columns(tmp_path: Path) -> None:
    db = DatabaseManager(str(tmp_path))
    db.initialize()
    with db.mol_conn() as conn:
        cols = {
            r["name"]: r for r in conn.execute("PRAGMA table_info(text_molecule_links)")
        }
    expected = {
        "id",
        "doc_id",
        "mol_id",
        "section_index",
        "page",
        "text_excerpt",
        "role",
        "code_text",
        "char_start",
        "char_end",
        "created_at",
    }
    assert expected <= set(cols)
    assert cols["role"]["dflt_value"] == "'mentioned'"
    assert cols["id"]["pk"] == 1
    assert cols["doc_id"]["notnull"] == 1
    assert cols["mol_id"]["notnull"] == 1


def test_sections_table_columns(tmp_path: Path) -> None:
    db = DatabaseManager(str(tmp_path))
    db.initialize()
    with db.kb_conn() as conn:
        cols = {r["name"]: r for r in conn.execute("PRAGMA table_info(sections)")}
    expected = {
        "id",
        "doc_id",
        "section_index",
        "title",
        "level",
        "char_start",
        "char_end",
        "page_start",
        "page_end",
        "paragraph_count",
        "molecule_count",
    }
    assert expected <= set(cols)
    assert cols["id"]["pk"] == 1
    assert cols["doc_id"]["notnull"] == 1
    assert cols["section_index"]["notnull"] == 1
    assert cols["level"]["dflt_value"] == "1"
    assert cols["paragraph_count"]["dflt_value"] == "0"
    assert cols["molecule_count"]["dflt_value"] == "0"


def test_text_molecule_links_index_exists(tmp_path: Path) -> None:
    db = DatabaseManager(str(tmp_path))
    db.initialize()
    with db.mol_conn() as conn:
        idx = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tml_doc_mol'"  # noqa: E501
            )
        }
    assert idx == {"idx_tml_doc_mol"}


def test_sections_index_exists(tmp_path: Path) -> None:
    db = DatabaseManager(str(tmp_path))
    db.initialize()
    with db.kb_conn() as conn:
        idx = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_sec_doc'"  # noqa: E501
            )
        }
    assert idx == {"idx_sec_doc"}


def test_text_molecule_links_insert_roundtrip(tmp_path: Path) -> None:
    db = DatabaseManager(str(tmp_path))
    db.initialize()
    with db.mol_conn() as conn:
        conn.execute(
            "INSERT INTO text_molecule_links (doc_id, mol_id, section_index, page, role, code_text) "  # noqa: E501
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("doc-1", "mol-A", 0, 3, "synthesized", "C(=O)=O"),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT doc_id, mol_id, role, code_text FROM text_molecule_links WHERE mol_id=?",  # noqa: E501
            ("mol-A",),
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["doc_id"] == "doc-1"
    assert rows[0]["role"] == "synthesized"
    assert rows[0]["code_text"] == "C(=O)=O"


def test_sections_insert_roundtrip(tmp_path: Path) -> None:
    db = DatabaseManager(str(tmp_path))
    db.initialize()
    with db.kb_conn() as conn:
        conn.execute(
            "INSERT INTO sections (doc_id, section_index, title, level, page_start, page_end) "  # noqa: E501
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("doc-1", 0, "Abstract", 1, 1, 1),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT title, level, page_start FROM sections WHERE doc_id=? ORDER BY section_index",  # noqa: E501
            ("doc-1",),
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["title"] == "Abstract"
    assert rows[0]["level"] == 1
    assert rows[0]["page_start"] == 1
