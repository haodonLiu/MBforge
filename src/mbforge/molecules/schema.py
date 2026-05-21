"""molecules/schema.py — MBForge 分子数据契约（唯一宪法）

所有模块（parsers, clustering, mcs, sar, csar_io, core/mol_database）
统一使用此 schema 作为输入输出格式。
不依赖 RDKit 以外的任何上层模块。
"""

from __future__ import annotations

import json
import logging
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

logger = logging.getLogger(__name__)

# RDKit 懒加载，避免模块级别 import
_RDKIT_AVAILABLE = True
try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors
except ImportError:
    _RDKIT_AVAILABLE = False


@dataclass
class Molecule:
    """分子数据契约（统一数据结构）。

    所有 parser/clustering/mcs/sar 模块输入输出均使用此对象。
    内部只存储可序列化的字段，RDKit Mol 对象通过 SMILES 懒加载重建。

    Attributes:
        id: 唯一标识符
        smiles: 标准 SMILES 字符串
        name: 分子名称或标识符
        source: 数据来源
        activity: 生物活性值 (IC50, Ki, EC50 等)
        activity_unit: 活性值单位 (nM, uM, mM)
        activity_raw: 原始活性值字符串
        cas: CAS 登记号
        cid: PubChem CID
        properties: 计算得到的理化性质
        tags: 用户自定义标签
        props: 从原始文件读取的额外属性
        metadata: 原始元数据（兼容旧格式）
        _rdkit_mol: 内部缓存，外部不可见
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    smiles: str = ""
    name: str = ""
    source: Literal["pdf", "sdf", "csv", "excel", "manual"] = "manual"
    activity: Optional[float] = None
    activity_unit: Optional[str] = None
    activity_raw: Optional[str] = None
    cas: Optional[str] = None
    cid: Optional[int] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    tags: Dict[str, Any] = field(default_factory=dict)
    props: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    _rdkit_mol: Optional[Any] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.mol is None and not self.smiles:
            raise ValueError("Molecule requires at least 'smiles' or '_rdkit_mol'")
        if self.mol is not None and not self.smiles:
            try:
                self.smiles = Chem.MolToSmiles(self.mol)
            except Exception as e:
                logger.warning(f"Failed to generate SMILES from mol: {e}")
        if self.mol is None and self.smiles:
            try:
                self._rdkit_mol = Chem.MolFromSmiles(self.smiles)
            except Exception:
                pass

    # ---- 懒加载 RDKit Mol 对象 ----

    @property
    def rdkit_mol(self) -> Optional[Any]:
        """从 SMILES 懒加载 RDKit Mol 对象，失败返回 None。"""
        if self._rdkit_mol is None and _RDKIT_AVAILABLE and self.smiles:
            try:
                self._rdkit_mol = Chem.MolFromSmiles(self.smiles)
            except Exception:
                self._rdkit_mol = None
        return self._rdkit_mol

    @rdkit_mol.setter
    def rdkit_mol(self, mol: Any) -> None:
        self._rdkit_mol = mol
        if mol is not None and _RDKIT_AVAILABLE:
            self.smiles = Chem.MolToSmiles(mol)

    @property
    def mol(self) -> Optional[Any]:
        """别名，兼容旧代码。"""
        return self.rdkit_mol

    def invalidate_rdk(self) -> None:
        self._rdkit_mol = None

    # ---- 工厂方法 ----

    @classmethod
    def from_smiles(cls, smiles: str, source: str = "manual", **kwargs: Any) -> "Molecule":
        return cls(smiles=smiles, source=source, **kwargs)

    @classmethod
    def from_mol(cls, mol: Any, name: str = "", **kwargs: Any) -> "Molecule":
        if mol is None:
            raise ValueError("RDKit Mol object cannot be None")
        smiles = Chem.MolToSmiles(mol)
        return cls(smiles=smiles, name=name or smiles, _rdkit_mol=mol, **kwargs)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Molecule":
        """从字典反序列化。兼容 schema 格式和旧 MoleculeEntry 格式。"""
        # 旧 MoleculeEntry 格式：{mol, smiles, name, activity, cas, props, ...}
        if "mol" in data or ("smiles" in data and "metadata" not in data and "id" not in data):
            mol = data.get("mol")
            smiles = data.get("smiles", "")
            # 顶层字段
            kwargs: Dict[str, Any] = {
                "name": data.get("name", ""),
                "activity": data.get("activity"),
                "activity_unit": data.get("activity_unit") or data.get("units"),
                "activity_raw": data.get("activity_raw"),
                "cas": data.get("cas"),
                "cid": data.get("cid"),
                "source": data.get("source", "sdf" if "props" in data else "manual"),
                "properties": data.get("properties", {}),
                "tags": data.get("tags", {}),
                "props": data.get("props", {}),
            }
            if mol is not None:
                return cls.from_mol(mol, **kwargs)
            return cls(smiles=smiles, **kwargs)
        # schema 标准格式
        known = {"id", "smiles", "name", "source", "activity", "activity_unit",
                 "activity_raw", "cas", "cid", "properties", "tags", "props", "metadata"}
        extra = {k: v for k, v in data.items() if k not in known}
        meta = {**data.get("metadata", {}), **extra}
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            smiles=data.get("smiles", ""),
            name=data.get("name", ""),
            source=data.get("source", "manual"),
            activity=data.get("activity"),
            activity_unit=data.get("activity_unit"),
            activity_raw=data.get("activity_raw"),
            cas=data.get("cas"),
            cid=data.get("cid"),
            properties=data.get("properties", {}),
            tags=data.get("tags", {}),
            props=data.get("props", {}),
            metadata=meta,
        )

    # ---- 导出方法 ----

    def to_dict(self) -> Dict[str, Any]:
        """序列化。输出格式与旧 MoleculeEntry.to_dict() 向后兼容。"""
        d: Dict[str, Any] = {
            "mol": self.mol,
            "smiles": self.smiles,
            "name": self.name,
            "activity": self.activity,
            "activity_raw": self.activity_raw,
            "cas": self.cas,
            "cid": self.cid,
            "properties": self.properties,
            "tags": self.tags,
            "source": self.source,
            "props": self.props,
        }
        if self.activity_unit is not None:
            d["activity_unit"] = self.activity_unit
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    # ---- 便捷方法 ----

    def copy(self) -> "Molecule":
        return Molecule(
            id=self.id,
            smiles=self.smiles,
            name=self.name,
            source=self.source,
            activity=self.activity,
            activity_unit=self.activity_unit,
            activity_raw=self.activity_raw,
            cas=self.cas,
            cid=self.cid,
            properties=deepcopy(self.properties),
            tags=deepcopy(self.tags),
            props=deepcopy(self.props),
            metadata=deepcopy(self.metadata),
            _rdkit_mol=Chem.Mol(self._rdkit_mol) if self._rdkit_mol is not None else None,
        )

    def has_activity(self) -> bool:
        return self.activity is not None

    def num_atoms(self) -> int:
        return self.mol.GetNumAtoms() if self.mol is not None else 0

    def num_bonds(self) -> int:
        return self.mol.GetNumBonds() if self.mol is not None else 0

    def molecular_weight(self) -> float:
        if self.mol is None:
            return 0.0
        return Descriptors.MolWt(self.mol)

    def logp(self) -> float:
        if self.mol is None:
            return 0.0
        return Descriptors.MolLogP(self.mol)

    # ---- 哈希与比较（基于 SMILES）----

    def __hash__(self) -> int:
        return hash(self.smiles)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Molecule):
            return NotImplemented
        return self.smiles == other.smiles

    def __repr__(self) -> str:
        return (
            f"Molecule(name={self.name!r}, smiles={self.smiles[:20]!r}, "
            f"activity={self.activity}, atoms={self.num_atoms()})"
        )


# ---- 向后兼容别名 ----
MoleculeEntry = Molecule


# ---- Batch 容器 ----

@dataclass
class MoleculeBatch:
    """分子列表的批量操作容器。

    提供过滤、排序、分组、去重、导出等批量操作。
    """

    entries: List[Molecule] = field(default_factory=list)

    @property
    def molecules(self) -> List[Molecule]:
        """别名，兼容旧代码。"""
        return self.entries

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)

    def __getitem__(self, idx: Union[int, slice]) -> Union[Molecule, List[Molecule]]:
        return self.entries[idx]

    def __contains__(self, item: Molecule) -> bool:
        return item in self.entries

    # ---- 增删 ----

    def append(self, entry: Molecule) -> None:
        self.entries.append(entry)

    def extend(self, entries: List[Molecule]) -> None:
        self.entries.extend(entries)

    # ---- 过滤 ----

    def filter_by(self, predicate) -> "MoleculeBatch":
        return MoleculeBatch([e for e in self.entries if predicate(e)])

    def filter_has_activity(self) -> "MoleculeBatch":
        return self.filter_by(lambda e: e.has_activity())

    def filter_by_smiles_length(self, max_len: int = 200) -> "MoleculeBatch":
        return MoleculeBatch([m for m in self.entries if len(m.smiles) <= max_len])

    def filter_by_size(self, min_atoms: Optional[int] = None, max_atoms: Optional[int] = None) -> "MoleculeBatch":
        def _pred(e: Molecule) -> bool:
            n = e.num_atoms()
            if min_atoms is not None and n < min_atoms:
                return False
            if max_atoms is not None and n > max_atoms:
                return False
            return True
        return self.filter_by(_pred)

    # ---- 排序 ----

    def sort_by(self, key, reverse: bool = False) -> "MoleculeBatch":
        return MoleculeBatch(sorted(self.entries, key=key, reverse=reverse))

    def sort_by_activity(self, ascending: bool = False) -> "MoleculeBatch":
        def _key(e: Molecule) -> float:
            return e.activity if e.activity is not None else float("inf")
        return self.sort_by(_key, reverse=not ascending)

    # ---- 分组 ----

    def group_by(self, key) -> Dict[Any, "MoleculeBatch"]:
        groups: Dict[Any, List[Molecule]] = {}
        for entry in self.entries:
            k = key(entry)
            groups.setdefault(k, []).append(entry)
        return {k: MoleculeBatch(v) for k, v in groups.items()}

    # ---- 去重 ----

    def deduplicate(self, key: str = "smiles") -> "MoleculeBatch":
        if key == "smiles":
            seen: Dict[str, List[Molecule]] = {}
            for entry in self.entries:
                seen.setdefault(entry.smiles, []).append(entry)
            deduped: List[Molecule] = []
            for smiles, group in seen.items():
                representative = group[0].copy()
                activities = [e.activity for e in group if e.activity is not None]
                if activities:
                    representative.activity = sum(activities) / len(activities)
                    representative.activity_raw = group[0].activity_raw
                deduped.append(representative)
            return MoleculeBatch(deduped)
        else:
            seen: Dict[str, Molecule] = {}
            for entry in self.entries:
                val = getattr(entry, key, "")
                if str(val) not in seen:
                    seen[str(val)] = entry
            return MoleculeBatch(list(seen.values()))

    # ---- 查询 ----

    def get_activities(self) -> List[float]:
        return [e.activity for e in self.entries if e.activity is not None]

    # ---- 导出 ----

    def to_dict_list(self) -> List[dict]:
        return [m.to_dict() for m in self.entries]

    def to_dicts(self) -> List[Dict[str, Any]]:
        """转换为旧版字典列表（向后兼容）。"""
        return [e.to_dict() for e in self.entries]

    def to_dataframe(self) -> Any:
        import pandas as pd
        records = []
        for e in self.entries:
            record: Dict[str, Any] = {
                "Name": e.name,
                "SMILES": e.smiles,
                "NumAtoms": e.num_atoms(),
                "NumBonds": e.num_bonds(),
                "MolecularWeight": e.molecular_weight(),
                "LogP": e.logp(),
            }
            if e.activity is not None:
                record["Activity"] = e.activity
            if e.activity_raw is not None:
                record["ActivityRaw"] = e.activity_raw
            if e.cas is not None:
                record["CAS"] = e.cas
            if e.cid is not None:
                record["CID"] = e.cid
            record.update(e.properties)
            records.append(record)
        return pd.DataFrame(records)

    def to_csv(self, path: Union[str, Path]) -> None:
        import pandas as pd
        records = []
        for m in self.entries:
            rec: Dict[str, Any] = {"SMILES": m.smiles}
            rec.update({k: v for k, v in m.metadata.items()
                        if k not in ("props", "properties", "tags")})
            mol = m.rdkit_mol
            if mol is not None and _RDKIT_AVAILABLE:
                rec["NumAtoms"] = mol.GetNumAtoms()
                rec["MolecularWeight"] = round(Descriptors.MolWt(mol), 2)
                rec["LogP"] = round(Descriptors.MolLogP(mol), 2)
            records.append(rec)
        pd.DataFrame(records).to_csv(path, index=False)

    def to_sdf(self, path: Union[str, Path]) -> None:
        if not _RDKIT_AVAILABLE:
            raise RuntimeError("RDKit is required for SDF export")
        with open(path, "wb") as f:
            writer = Chem.SDWriter(f)
            for m in self.entries:
                mol = m.rdkit_mol
                if mol is not None:
                    mol_copy = Chem.Mol(mol)
                    if m.name:
                        mol_copy.SetProp("_Name", str(m.name))
                    for k, v in m.props.items():
                        mol_copy.SetProp(str(k), str(v))
                    if m.activity is not None:
                        mol_copy.SetProp("Activity", str(m.activity))
                    if m.cas is not None:
                        mol_copy.SetProp("CAS", str(m.cas))
                    if m.cid is not None:
                        mol_copy.SetProp("CID", str(m.cid))
                    writer.write(mol_copy)
            writer.close()

    def to_excel(self, path: Union[str, Path]) -> None:
        df = self.to_dataframe()
        df.to_excel(path, index=False)

    @classmethod
    def from_smiles_list(cls, smiles_list: List[str], source: str = "manual") -> "MoleculeBatch":
        return cls([Molecule.from_smiles(s, source=source) for s in smiles_list])

    def __repr__(self) -> str:
        return f"MoleculeBatch(n={len(self.entries)})"
