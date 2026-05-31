"""测试分子数据库模块."""

import tempfile
from pathlib import Path


from mbforge.core.mol_database import MoleculeDatabase, MoleculeRecord


class TestMoleculeDatabase:
    def test_add_and_get(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MoleculeDatabase(Path(tmpdir))
            try:
                rec = MoleculeRecord(
                    mol_id="mol-001",
                    esmiles="CCO",
                    name="Ethanol",
                    activity=100.0,
                    activity_type="IC50",
                )
                db.add_molecule(rec)
                found = db.get_molecule("mol-001")
                assert found is not None
                assert found.name == "Ethanol"
            finally:
                db.close()

    def test_search_by_esmiles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MoleculeDatabase(Path(tmpdir))
            try:
                rec = MoleculeRecord(mol_id="mol-002", esmiles="c1ccccc1", name="Benzene")
                db.add_molecule(rec)
                found = db.search_by_esmiles("c1ccccc1")
                assert found is not None
                assert found.name == "Benzene"
            finally:
                db.close()

    def test_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = MoleculeDatabase(Path(tmpdir))
            try:
                db.add_molecule(MoleculeRecord(mol_id="m1", esmiles="C", activity=10.0))
                stats = db.get_stats()
                assert stats["total"] == 1
                assert stats["with_activity"] == 1
            finally:
                db.close()
