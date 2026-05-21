"""分子数据模型.

提供统一、类型安全的分子数据容器，替代项目中原有的裸字典传递方式。

核心类:
    MoleculeEntry: 单个分子的完整数据记录
    MoleculeBatch: 分子列表的批量操作容器
"""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from rdkit import Chem
from rdkit.Chem import Descriptors

logger = logging.getLogger(__name__)


@dataclass
class MoleculeEntry:
    """单个分子的完整数据记录.

    作为项目中分子数据的统一数据模型，替代原有的 Dict[str, Any] 字典传递方式。
    所有字段均有类型注解，便于静态类型检查和 IDE 自动补全。

    属性:
        mol: RDKit 分子对象 (可选，若 SMILES 有效则可延迟解析).
        smiles: Canonical SMILES 字符串.
        name: 分子名称或标识符.
        activity: 生物活性值 (如 IC50, Ki, EC50 等).
        activity_unit: 活性值单位 (如 "nM", "uM", "mM").
        activity_raw: 原始活性值字符串（保留原始记录）.
        cas: CAS 登记号.
        cid: PubChem CID.
        properties: 计算得到的理化性质字典.
        tags: 用户自定义标签字典.
        source: 数据来源标识.
        props: 从原始文件读取的额外属性字典.
    """

    smiles: str = ""
    mol: Optional[Chem.Mol] = None
    name: str = ""
    activity: Optional[float] = None
    activity_unit: Optional[str] = None
    activity_raw: Optional[str] = None
    cas: Optional[str] = None
    cid: Optional[int] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    tags: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    props: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """初始化后校验：确保 mol 和 smiles 至少有一个有效."""
        if self.mol is None and not self.smiles:
            raise ValueError("MoleculeEntry requires at least 'mol' or 'smiles'")
        # 如果提供了 mol 但没有 smiles，自动生成
        if self.mol is not None and not self.smiles:
            try:
                self.smiles = Chem.MolToSmiles(self.mol)
            except Exception as e:
                logger.warning(f"Failed to generate SMILES from mol: {e}")
        # 如果提供了 smiles 但没有 mol，延迟解析
        if self.mol is None and self.smiles:
            self.mol = Chem.MolFromSmiles(self.smiles)
            if self.mol is None:
                raise ValueError(f"Invalid SMILES: {self.smiles}")

    # ------------------------------------------------------------------
    # 工厂方法
    # ------------------------------------------------------------------

    @classmethod
    def from_smiles(
        cls,
        smiles: str,
        name: str = "",
        **kwargs: Any,
    ) -> MoleculeEntry:
        """从 SMILES 字符串创建分子记录.

        Args:
            smiles: SMILES 字符串.
            name: 分子名称.
            **kwargs: 其他可选字段.

        Returns:
            初始化后的 MoleculeEntry 实例.

        Raises:
            ValueError: SMILES 无效时抛出.
        """
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES: {smiles}")
        return cls(smiles=smiles, mol=mol, name=name or smiles, **kwargs)

    @classmethod
    def from_mol(
        cls,
        mol: Chem.Mol,
        name: str = "",
        **kwargs: Any,
    ) -> MoleculeEntry:
        """从 RDKit Mol 对象创建分子记录.

        Args:
            mol: RDKit 分子对象.
            name: 分子名称.
            **kwargs: 其他可选字段.

        Returns:
            初始化后的 MoleculeEntry 实例.

        Raises:
            ValueError: Mol 对象无效时抛出.
        """
        if mol is None:
            raise ValueError("RDKit Mol object cannot be None")
        smiles = Chem.MolToSmiles(mol)
        return cls(mol=mol, smiles=smiles, name=name or smiles, **kwargs)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MoleculeEntry:
        """从旧版字典创建分子记录（向后兼容）.

        支持旧版 reader/writer 使用的字典格式：
        - "mol": RDKit Mol 对象
        - "smiles": SMILES 字符串
        - "name": 名称
        - "activity": 活性值
        - "activity_raw": 原始活性字符串
        - "cas": CAS 号
        - "props": 额外属性字典

        Args:
            data: 旧版分子字典.

        Returns:
            转换后的 MoleculeEntry 实例.
        """
        kwargs: Dict[str, Any] = {}
        if "activity" in data:
            kwargs["activity"] = data["activity"]
        if "activity_raw" in data:
            kwargs["activity_raw"] = data["activity_raw"]
        if "cas" in data:
            kwargs["cas"] = data["cas"]
        if "props" in data:
            kwargs["props"] = data.get("props", {})
        if "cid" in data:
            kwargs["cid"] = data["cid"]
        if "source" in data:
            kwargs["source"] = data["source"]

        mol = data.get("mol")
        smiles = data.get("smiles", "")
        name = data.get("name", "")

        if mol is not None:
            return cls.from_mol(mol, name=name, **kwargs)
        elif smiles:
            return cls.from_smiles(smiles, name=name, **kwargs)
        else:
            raise ValueError("Dictionary must contain 'mol' or 'smiles' key")

    # ------------------------------------------------------------------
    # 实用方法
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（向后兼容）.

        Returns:
            包含所有字段的字典.
        """
        return {
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

    def copy(self) -> MoleculeEntry:
        """深拷贝分子记录.

        Returns:
            新的 MoleculeEntry 实例（mol 对象也会复制）.
        """
        new_entry = MoleculeEntry(
            smiles=self.smiles,
            mol=Chem.Mol(self.mol) if self.mol is not None else None,
            name=self.name,
            activity=self.activity,
            activity_unit=self.activity_unit,
            activity_raw=self.activity_raw,
            cas=self.cas,
            cid=self.cid,
            properties=deepcopy(self.properties),
            tags=deepcopy(self.tags),
            source=self.source,
            props=deepcopy(self.props),
        )
        return new_entry

    def has_activity(self) -> bool:
        """检查是否有有效活性值.

        Returns:
            activity 不为 None 且为有效数值时返回 True.
        """
        return self.activity is not None

    def num_atoms(self) -> int:
        """获取原子数（惰性计算，mol 为 None 时返回 0）.

        Returns:
            分子中的原子数量.
        """
        return self.mol.GetNumAtoms() if self.mol is not None else 0

    def num_bonds(self) -> int:
        """获取键数.

        Returns:
            分子中的键数量.
        """
        return self.mol.GetNumBonds() if self.mol is not None else 0

    def molecular_weight(self) -> float:
        """计算分子量（mol 为 None 时返回 0.0）.

        Returns:
            分子量.
        """
        if self.mol is None:
            return 0.0
        return Descriptors.MolWt(self.mol)

    def logp(self) -> float:
        """计算脂水分配系数 LogP.

        Returns:
            LogP 值.
        """
        if self.mol is None:
            return 0.0
        return Descriptors.MolLogP(self.mol)

    def __hash__(self) -> int:
        """基于 SMILES 的哈希值（用于集合和字典）."""
        return hash(self.smiles)

    def __eq__(self, other: object) -> bool:
        """基于 SMILES 的相等性比较."""
        if not isinstance(other, MoleculeEntry):
            return NotImplemented
        return self.smiles == other.smiles

    def __repr__(self) -> str:
        """简洁的字符串表示."""
        return (
            f"MoleculeEntry(name={self.name!r}, smiles={self.smiles!r}, "
            f"activity={self.activity}, atoms={self.num_atoms()})"
        )


class MoleculeBatch:
    """分子列表的批量操作容器.

    提供对分子集合的高级操作：过滤、映射、排序、分组、去重等。
    旨在简化对大量分子的批量处理流程。

    属性:
        entries: MoleculeEntry 列表.
    """

    def __init__(self, entries: Optional[List[MoleculeEntry]] = None) -> None:
        """初始化分子批次.

        Args:
            entries: 初始分子列表，默认为空列表.
        """
        self.entries: List[MoleculeEntry] = list(entries) if entries is not None else []

    # ------------------------------------------------------------------
    # 序列协议支持
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)

    def __getitem__(self, idx: Union[int, slice]) -> Union[MoleculeEntry, List[MoleculeEntry]]:
        return self.entries[idx]

    def __contains__(self, item: MoleculeEntry) -> bool:
        return item in self.entries

    # ------------------------------------------------------------------
    # 批量操作
    # ------------------------------------------------------------------

    def append(self, entry: MoleculeEntry) -> None:
        """添加单个分子记录."""
        self.entries.append(entry)

    def extend(self, entries: List[MoleculeEntry]) -> None:
        """批量添加分子记录."""
        self.entries.extend(entries)

    def deduplicate(self, key: str = "smiles") -> MoleculeBatch:
        """按指定键去重并取活性平均值（当 key="smiles" 时）.

        Args:
            key: 去重依据的字段名，默认为 "smiles".

        Returns:
            去重后的新 MoleculeBatch.
        """
        if key == "smiles":
            seen: Dict[str, List[MoleculeEntry]] = {}
            for entry in self.entries:
                seen.setdefault(entry.smiles, []).append(entry)

            deduped: List[MoleculeEntry] = []
            for smiles, group in seen.items():
                representative = group[0].copy()
                activities = [e.activity for e in group if e.activity is not None]
                if activities:
                    representative.activity = sum(activities) / len(activities)
                    representative.activity_raw = group[0].activity_raw
                deduped.append(representative)
            return MoleculeBatch(deduped)
        else:
            # 通用去重
            seen: Dict[str, MoleculeEntry] = {}
            for entry in self.entries:
                val = getattr(entry, key, "")
                if val not in seen:
                    seen[str(val)] = entry
            return MoleculeBatch(list(seen.values()))

    def filter_by(
        self,
        predicate,
    ) -> MoleculeBatch:
        """按谓词函数过滤分子.

        Args:
            predicate: 接受 MoleculeEntry 返回 bool 的函数.

        Returns:
            过滤后的新 MoleculeBatch.
        """
        return MoleculeBatch([e for e in self.entries if predicate(e)])

    def filter_has_activity(self) -> MoleculeBatch:
        """过滤掉没有活性值的分子.

        Returns:
            仅包含有活性值分子的新 MoleculeBatch.
        """
        return self.filter_by(lambda e: e.has_activity())

    def filter_by_size(
        self,
        min_atoms: Optional[int] = None,
        max_atoms: Optional[int] = None,
    ) -> MoleculeBatch:
        """按原子数范围过滤.

        Args:
            min_atoms: 最小原子数（含）.
            max_atoms: 最大原子数（含）.

        Returns:
            过滤后的新 MoleculeBatch.
        """

        def _pred(e: MoleculeEntry) -> bool:
            n = e.num_atoms()
            if min_atoms is not None and n < min_atoms:
                return False
            if max_atoms is not None and n > max_atoms:
                return False
            return True

        return self.filter_by(_pred)

    def sort_by(
        self,
        key,
        reverse: bool = False,
    ) -> MoleculeBatch:
        """按指定键排序.

        Args:
            key: 排序键函数（接受 MoleculeEntry）.
            reverse: 是否降序，默认为 False.

        Returns:
            排序后的新 MoleculeBatch.
        """
        return MoleculeBatch(sorted(self.entries, key=key, reverse=reverse))

    def sort_by_activity(self, reverse: bool = False) -> MoleculeBatch:
        """按活性值排序（无活性的排在最后）.

        Args:
            reverse: 是否降序，默认为 False.

        Returns:
            排序后的新 MoleculeBatch.
        """
        def _key(e: MoleculeEntry) -> float:
            return e.activity if e.activity is not None else float("inf")
        return self.sort_by(_key, reverse=reverse)

    def group_by(self, key) -> Dict[Any, MoleculeBatch]:
        """按指定键分组.

        Args:
            key: 分组键函数（接受 MoleculeEntry）.

        Returns:
            键 -> MoleculeBatch 的字典.
        """
        groups: Dict[Any, List[MoleculeEntry]] = {}
        for entry in self.entries:
            k = key(entry)
            groups.setdefault(k, []).append(entry)
        return {k: MoleculeBatch(v) for k, v in groups.items()}

    def get_activities(self) -> List[float]:
        """获取所有有效活性值列表.

        Returns:
            活性值列表（自动过滤 None）.
        """
        return [e.activity for e in self.entries if e.activity is not None]

    def to_dataframe(self) -> Any:
        """转换为 pandas DataFrame.

        Returns:
            包含分子数据的 DataFrame.
        """
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

    def to_dicts(self) -> List[Dict[str, Any]]:
        """转换为旧版字典列表（向后兼容）.

        Returns:
            字典列表，可直接传给现有 writer.
        """
        return [e.to_dict() for e in self.entries]

    def to_csv(self, path: Union[str, Path]) -> None:
        """将批次导出为 CSV 文件.

        Args:
            path: 输出 CSV 文件路径.
        """
        path = Path(path)
        df = self.to_dataframe()
        df.to_csv(path, index=False)

    def to_sdf(self, path: Union[str, Path]) -> None:
        """将批次导出为 SDF 文件.

        Args:
            path: 输出 SDF 文件路径.
        """
        path = Path(path)
        with open(path, "wb") as f:
            writer = Chem.SDWriter(f)
            for entry in self.entries:
                if entry.mol is not None:
                    mol = Chem.Mol(entry.mol)
                    # 写入自定义属性
                    for prop, value in entry.props.items():
                        mol.SetProp(str(prop), str(value))
                    if entry.activity is not None:
                        mol.SetProp("Activity", str(entry.activity))
                    if entry.cas is not None:
                        mol.SetProp("CAS", str(entry.cas))
                    if entry.cid is not None:
                        mol.SetProp("CID", str(entry.cid))
                    if entry.name:
                        mol.SetProp("_Name", str(entry.name))
                    writer.write(mol)
            writer.close()

    def to_excel(self, path: Union[str, Path]) -> None:
        """将批次导出为 Excel 文件.

        Args:
            path: 输出 Excel 文件路径.
        """
        path = Path(path)
        df = self.to_dataframe()
        df.to_excel(path, index=False)

    def __repr__(self) -> str:
        return f"MoleculeBatch(n={len(self.entries)})"
