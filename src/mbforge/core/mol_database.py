"""分子数据库 - SQLite 存储 + RDKit 化学信息学支持.

为后续分子生成/对接/QSAR/MD 预留扩展接口。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Draw, AllChem
except ImportError:
    Chem = None  # type: ignore
    Descriptors = None  # type: ignore
    Draw = None  # type: ignore
    AllChem = None  # type: ignore

from ..utils.constants import MOL_DB_FILENAME, PROJECT_META_DIR


@dataclass
class MoleculeRecord:
    """分子记录."""

    mol_id: str
    smiles: str
    name: str = ""
    source_doc: str = ""  # 来源文档ID
    activity: Optional[float] = None
    activity_type: str = ""  # IC50, EC50, Ki, etc.
    units: str = "nM"
    properties: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mol_id": self.mol_id,
            "smiles": self.smiles,
            "name": self.name,
            "source_doc": self.source_doc,
            "activity": self.activity,
            "activity_type": self.activity_type,
            "units": self.units,
            "properties": self.properties,
            "tags": self.tags,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MoleculeRecord:
        return cls(
            mol_id=data["mol_id"],
            smiles=data["smiles"],
            name=data.get("name", ""),
            source_doc=data.get("source_doc", ""),
            activity=data.get("activity"),
            activity_type=data.get("activity_type", ""),
            units=data.get("units", "nM"),
            properties=data.get("properties", {}),
            tags=data.get("tags", []),
            notes=data.get("notes", ""),
        )

    @property
    def mol(self):
        """RDKit Mol 对象."""
        if Chem is None:
            return None
        return Chem.MolFromSmiles(self.smiles)

    def compute_properties(self) -> Dict[str, float]:
        """计算基本分子性质."""
        if Chem is None or Descriptors is None:
            return {}
        m = self.mol
        if m is None:
            return {}
        props = {
            "MW": Descriptors.MolWt(m),
            "LogP": Descriptors.MolLogP(m),
            "HBD": Descriptors.NumHDonors(m),
            "HBA": Descriptors.NumHAcceptors(m),
            "TPSA": Descriptors.TPSA(m),
            "RotatableBonds": Descriptors.NumRotatableBonds(m),
        }
        return props

    def to_molecule(self):
        """转换为 schema.Molecule 对象。"""
        from ..molecules.schema import Molecule
        return Molecule(
            id=self.mol_id,
            smiles=self.smiles,
            name=self.name,
            source="pdf" if self.source_doc else "manual",
            activity=self.activity,
            activity_unit=self.units,
            cas=self.tags[0] if self.tags else None,
            properties=self.properties,
        )

    @classmethod
    def from_molecule(cls, mol) -> "MoleculeRecord":
        """从 schema.Molecule 创建 MoleculeRecord。"""
        return cls(
            mol_id=mol.id,
            smiles=mol.smiles,
            name=mol.name,
            activity=mol.activity,
            activity_type="IC50",
            units=mol.activity_unit or "nM",
            properties=mol.properties,
            tags=[mol.cas] if mol.cas else [],
        )


class MoleculeDatabase:
    """分子数据库管理器."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS molecules (
        mol_id TEXT PRIMARY KEY,
        smiles TEXT NOT NULL,
        name TEXT,
        source_doc TEXT,
        activity REAL,
        activity_type TEXT,
        units TEXT DEFAULT 'nM',
        properties TEXT,  -- JSON
        tags TEXT,        -- JSON array
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_smiles ON molecules(smiles);
    CREATE INDEX IF NOT EXISTS idx_source ON molecules(source_doc);
    CREATE INDEX IF NOT EXISTS idx_activity ON molecules(activity);
    CREATE VIRTUAL TABLE IF NOT EXISTS mol_search USING fts5(
        name, notes, smiles, content='molecules', content_rowid='rowid'
    );
    """

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.db_path = self.project_root / PROJECT_META_DIR / MOL_DB_FILENAME
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript(self.SCHEMA)
        self._conn.commit()

    def add_molecule(self, record: MoleculeRecord) -> None:
        """添加或更新分子记录."""
        # 计算性质
        if not record.properties:
            record.properties = record.compute_properties()

        try:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO molecules
                (mol_id, smiles, name, source_doc, activity, activity_type, units, properties, tags, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.mol_id,
                    record.smiles,
                    record.name,
                    record.source_doc,
                    record.activity,
                    record.activity_type,
                    record.units,
                    json.dumps(record.properties, ensure_ascii=False),
                    json.dumps(record.tags, ensure_ascii=False),
                    record.notes,
                ),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def get_molecule(self, mol_id: str) -> Optional[MoleculeRecord]:
        row = self._conn.execute(
            "SELECT * FROM molecules WHERE mol_id = ?", (mol_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def search_by_smiles(self, smiles: str) -> Optional[MoleculeRecord]:
        row = self._conn.execute(
            "SELECT * FROM molecules WHERE smiles = ?", (smiles,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def search_by_source(self, doc_id: str) -> List[MoleculeRecord]:
        rows = self._conn.execute(
            "SELECT * FROM molecules WHERE source_doc = ?", (doc_id,)
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def search_by_activity_range(
        self, min_val: float, max_val: float, activity_type: str = ""
    ) -> List[MoleculeRecord]:
        if activity_type:
            rows = self._conn.execute(
                "SELECT * FROM molecules WHERE activity BETWEEN ? AND ? AND activity_type = ?",
                (min_val, max_val, activity_type),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM molecules WHERE activity BETWEEN ? AND ?",
                (min_val, max_val),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def list_all(self, limit: int = 1000) -> List[MoleculeRecord]:
        rows = self._conn.execute(
            "SELECT * FROM molecules ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def delete_molecule(self, mol_id: str) -> None:
        self._conn.execute("DELETE FROM molecules WHERE mol_id = ?", (mol_id,))
        self._conn.commit()

    def get_stats(self) -> Dict[str, Any]:
        total = self._conn.execute("SELECT COUNT(*) FROM molecules").fetchone()[0]
        with_activity = self._conn.execute(
            "SELECT COUNT(*) FROM molecules WHERE activity IS NOT NULL"
        ).fetchone()[0]
        return {
            "total": total,
            "with_activity": with_activity,
        }

    def _row_to_record(self, row: sqlite3.Row) -> MoleculeRecord:
        data = dict(row)
        data["properties"] = json.loads(data.get("properties", "{}"))
        data["tags"] = json.loads(data.get("tags", "[]"))
        return MoleculeRecord.from_dict(data)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
