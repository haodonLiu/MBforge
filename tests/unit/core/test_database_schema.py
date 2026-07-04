from pathlib import Path

from mbforge.core.database import DatabaseManager


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
