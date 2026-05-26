"""分子数据库 - SQLite 存储 + RDKit 化学信息学支持.

为后续分子生成/对接/QSAR/MD 预留扩展接口。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

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
    activity: float | None = None
    activity_type: str = ""  # IC50, EC50, Ki, etc.
    units: str = "nM"
    source_type: Literal["image", "text", "manual"] = "text"
    status: Literal["pending", "confirmed", "rejected"] = "confirmed"
    properties: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mol_id": self.mol_id,
            "smiles": self.smiles,
            "name": self.name,
            "source_doc": self.source_doc,
            "activity": self.activity,
            "activity_type": self.activity_type,
            "units": self.units,
            "source_type": self.source_type,
            "status": self.status,
            "properties": self.properties,
            "tags": self.tags,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MoleculeRecord:
        return cls(
            mol_id=data["mol_id"],
            smiles=data["smiles"],
            name=data.get("name", ""),
            source_doc=data.get("source_doc", ""),
            activity=data.get("activity"),
            activity_type=data.get("activity_type", ""),
            units=data.get("units", "nM"),
            source_type=data.get("source_type", "text"),
            status=data.get("status", "confirmed"),
            properties=data.get("properties", {}),
            tags=data.get("tags", []),
            notes=data.get("notes", ""),
        )

    @property
    def mol(self):
        """RDKit Mol 对象（带缓存）."""
        if not hasattr(self, "_cached_mol"):
            self._cached_mol = Chem.MolFromSmiles(self.smiles) if Chem else None
        return self._cached_mol

    def compute_properties(self) -> dict[str, float]:
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
            source=self.source_type or ("pdf" if self.source_doc else "manual"),
            activity=self.activity,
            activity_unit=self.units,
            cas=self.tags[0] if self.tags else None,
            properties=self.properties,
        )

    @classmethod
    def from_molecule(cls, mol, activity_type: str = "") -> MoleculeRecord:
        """从 schema.Molecule 创建 MoleculeRecord。"""
        return cls(
            mol_id=mol.id,
            smiles=mol.smiles,
            name=mol.name,
            activity=mol.activity,
            activity_type=activity_type or mol.metadata.get("activity_type", ""),
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
        source_type TEXT DEFAULT 'text',
        status TEXT DEFAULT 'confirmed',
        properties TEXT,  -- JSON
        tags TEXT,        -- JSON array
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_smiles ON molecules(smiles);
    CREATE INDEX IF NOT EXISTS idx_source ON molecules(source_doc);
    CREATE INDEX IF NOT EXISTS idx_activity ON molecules(activity);
    -- idx_source_type / idx_status 在 _ensure_columns() 中创建，避免旧数据库缺列报错
    CREATE VIRTUAL TABLE IF NOT EXISTS mol_search USING fts5(
        name, notes, smiles, content='molecules', content_rowid='rowid'
    );
    """

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.db_path = self.project_root / PROJECT_META_DIR / MOL_DB_FILENAME
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._init_db()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception(
                "MoleculeDatabase 初始化失败: db_path=%s error=%s", self.db_path, exc
            )
            self._conn = None
            raise

    def _init_db(self) -> None:
        # 分步执行，避免旧数据库缺少新列导致 CREATE INDEX 失败
        self._conn.executescript(self.SCHEMA)
        self._ensure_columns()
        self._conn.commit()

    def _ensure_columns(self) -> None:
        """确保所有列存在（向后兼容旧数据库）。"""
        cursor = self._conn.execute("PRAGMA table_info(molecules)")
        columns = {row["name"] for row in cursor.fetchall()}

        for col_def in [
            "source_type TEXT DEFAULT 'text'",
            "status TEXT DEFAULT 'confirmed'",
        ]:
            col_name = col_def.split()[0]
            if col_name not in columns:
                self._conn.execute(f"ALTER TABLE molecules ADD COLUMN {col_def}")

        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_source_type ON molecules(source_type)",
            "CREATE INDEX IF NOT EXISTS idx_status ON molecules(status)",
        ]:
            try:
                self._conn.execute(idx_sql)
            except sqlite3.OperationalError:
                pass

    def add_molecule(self, record: MoleculeRecord) -> None:
        """添加或更新分子记录."""
        # 计算性质
        if not record.properties:
            record.properties = record.compute_properties()

        try:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO molecules
                (mol_id, smiles, name, source_doc, activity, activity_type, units, source_type, status, properties, tags, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.mol_id,
                    record.smiles,
                    record.name,
                    record.source_doc,
                    record.activity,
                    record.activity_type,
                    record.units,
                    record.source_type,
                    record.status,
                    json.dumps(record.properties, ensure_ascii=False),
                    json.dumps(record.tags, ensure_ascii=False),
                    record.notes,
                ),
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def get_molecule(self, mol_id: str) -> MoleculeRecord | None:
        row = self._conn.execute(
            "SELECT * FROM molecules WHERE mol_id = ?", (mol_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def search_by_smiles(self, smiles: str) -> MoleculeRecord | None:
        row = self._conn.execute(
            "SELECT * FROM molecules WHERE smiles = ?", (smiles,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def search_by_source(self, doc_id: str) -> list[MoleculeRecord]:
        rows = self._conn.execute(
            "SELECT * FROM molecules WHERE source_doc = ?", (doc_id,)
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def search_by_activity_range(
        self, min_val: float, max_val: float, activity_type: str = ""
    ) -> list[MoleculeRecord]:
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

    def list_all(
        self,
        limit: int = 1000,
        source_type: str | None = None,
        status: str | None = None,
    ) -> list[MoleculeRecord]:
        """列出分子记录，支持按来源和状态过滤.

        Args:
            limit: 最大返回数量
            source_type: 过滤来源类型 ('image'|'text'|'manual')
            status: 过滤状态 ('pending'|'confirmed'|'rejected')
        """
        conditions: list[str] = []
        params: list[Any] = []
        if source_type:
            conditions.append("source_type = ?")
            params.append(source_type)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT * FROM molecules {where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        if self._conn is None:
            raise RuntimeError("MoleculeDatabase 未初始化：数据库连接失败。")
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_record(r) for r in rows]

    def delete_molecule(self, mol_id: str) -> None:
        if self._conn is None:
            raise RuntimeError("MoleculeDatabase 未初始化：数据库连接失败。")
        self._conn.execute("DELETE FROM molecules WHERE mol_id = ?", (mol_id,))
        self._conn.commit()

    def get_stats(self) -> dict[str, Any]:
        if self._conn is None:
            raise RuntimeError("MoleculeDatabase 未初始化：数据库连接失败。")
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
