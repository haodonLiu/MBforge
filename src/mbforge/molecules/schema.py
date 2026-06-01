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
from typing import Any, Literal, Union

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
        esmiles: 标准 E-SMILES 字符串
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
        _mol: 内部缓存的 RDKit Mol 对象
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    esmiles: str = ""
    name: str = ""
    source: Literal["pdf", "sdf", "csv", "excel", "manual"] = "manual"
    activity: float | None = None
    activity_unit: str | None = None
    activity_raw: str | None = None
    cas: str | None = None
    cid: int | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    tags: dict[str, Any] = field(default_factory=dict)
    props: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    _mol: Any | None = field(default=None, repr=False)
    _mol_parse_attempted: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        if self._mol is None and not self.esmiles:
            raise ValueError("Molecule requires at least 'esmiles' or '_mol'")
        if self._mol is not None and not self.esmiles:
            try:
                self.esmiles = Chem.MolToSmiles(self._mol)
            except Exception as e:
                logger.warning(f"Failed to generate SMILES from mol: {e}")

    # ---- 懒加载 RDKit Mol 对象 ----

    @property
    def mol(self) -> Any | None:
        """从 SMILES 懒加载 RDKit Mol 对象，失败返回 None。"""
        if not self._mol_parse_attempted and _RDKIT_AVAILABLE and self.esmiles:
            self._mol_parse_attempted = True
            try:
                self._mol = Chem.MolFromSmiles(self.esmiles)
            except Exception:
                self._mol = None
        return self._mol

    @mol.setter
    def mol(self, value: Any) -> None:
        self._mol = value
        if value is not None and _RDKIT_AVAILABLE:
            self.esmiles = Chem.MolToSmiles(value)

    def clear_mol_cache(self) -> None:
        self._mol = None
        self._mol_parse_attempted = False

    # ---- 工厂方法 ----

    @classmethod
    def from_smiles(
        cls, esmiles: str, source: str = "manual", **kwargs: Any
    ) -> Molecule:
        return cls(esmiles=esmiles, source=source, **kwargs)

    @classmethod
    def from_mol(cls, mol: Any, name: str = "", **kwargs: Any) -> Molecule:
        if mol is None:
            raise ValueError("RDKit Mol object cannot be None")
        esmiles = Chem.MolToSmiles(mol)
        return cls(esmiles=esmiles, name=name or esmiles, _mol=mol, **kwargs)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Molecule:
        """从字典反序列化。兼容 schema 格式和旧 reader 格式。"""
        # 旧 reader 格式：{mol, esmiles, name, activity, cas, props, ...}
        if "mol" in data or (
            "esmiles" in data and "metadata" not in data and "id" not in data
        ):
            mol = data.get("mol")
            esmiles_str = data.get("esmiles", "") or data.get("smiles", "")
            kwargs: dict[str, Any] = {
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
            return cls(esmiles=esmiles_str, **kwargs)
        # schema 标准格式
        known = {
            "id",
            "esmiles",
            "smiles",
            "name",
            "source",
            "activity",
            "activity_unit",
            "activity_raw",
            "cas",
            "cid",
            "properties",
            "tags",
            "props",
            "metadata",
        }
        extra = {k: v for k, v in data.items() if k not in known}
        meta = {**data.get("metadata", {}), **extra}
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            esmiles=data.get("esmiles", "") or data.get("smiles", ""),
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

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON-safe 字典。"""
        d: dict[str, Any] = {
            "esmiles": self.esmiles,
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
        return json.dumps(self.to_dict(), ensure_ascii=False)

    # ---- 便捷方法 ----

    def copy(self) -> Molecule:
        return Molecule(
            id=self.id,
            esmiles=self.esmiles,
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
            _mol=Chem.Mol(self._mol) if self._mol is not None else None,
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
        return hash(self.esmiles)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Molecule):
            return NotImplemented
        return self.esmiles == other.esmiles

    def __repr__(self) -> str:
        return (
            f"Molecule(name={self.name!r}, esmiles={self.esmiles[:20]!r}, "
            f"activity={self.activity}, atoms={self.num_atoms()})"
        )



