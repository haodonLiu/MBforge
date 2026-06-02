"""SAR (Structure-Activity Relationship) 分析核心模块.

提供：
- 共同骨架提取（基于 RDKit FindMCS）
- R-group 分解：识别每个分子在骨架上的取代基
- R-group 矩阵：化合物 × 取代基位置 的二维表
- 活性热力图数据：取代基 × 活性的颜色编码

依赖：RDKit (>= 2024.3)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

try:
    from rdkit import Chem, RDLogger
    from rdkit.Chem import (
        AllChem,
        rdFMCS,  # noqa: N816  # RDKit 命名约定
    )

    RDLogger.DisableLog("rdApp.*")  # 静默 RDKit 警告
    _RDKIT_AVAILABLE = True
except ImportError:
    Chem = None  # type: ignore
    AllChem = None  # type: ignore
    rdFMCS = None  # type: ignore  # noqa: N816
    _RDKIT_AVAILABLE = False
# E-SMILES 标记符（如 <c>1:R1</c>）剥离正则
_ESMILES_TAG_RE = re.compile(r"<[a-zA-Z]>\d+:[^<]+</[a-zA-Z]>")
_DUMMY_ATOM_NUM = re.compile(r"\[(\d+)\*?\]")  # [*] 或 [1*] 形式的 R 位点


@dataclass
class RGroupEntry:
    """单个分子在某骨架位置上的取代基.

    Attributes:
        position: 骨架上原子的索引（在 core_smiles 中的位置）
        label: 取代基标签（如 "R1"、"R2"）
        substituent_smiles: 取代基的 SMILES（不含骨架原子）
        substituent_atoms: 取代基中重原子数（不含骨架原子）
    """

    position: int
    label: str
    substituent_smiles: str
    substituent_atoms: int = 0


@dataclass
class RGroupDecomposition:
    """单个分子的 R-group 分解结果.

    Attributes:
        compound_id: 化合物 ID
        compound_name: 化合物名称
        smiles: 原始 SMILES
        core_matches: 是否能匹配上骨架（True=在骨架上 / False=不匹配）
        r_groups: 该分子的 R-group 列表
    """

    compound_id: str
    compound_name: str
    smiles: str
    core_matches: bool
    r_groups: list[RGroupEntry] = field(default_factory=list)


@dataclass
class RGroupMatrix:
    """R-group 矩阵.

    Attributes:
        core_smiles: 共同骨架 SMILES
        r_labels: 取代基标签列表（列），如 ["R1", "R2"]
        rows: 每行 = 一个化合物，顺序对齐 columns
        compounds: 化合物元数据（id, name, activity, activity_type, units, matches）
    """

    core_smiles: str
    r_labels: list[str]
    rows: list[list[str]]  # rows[i][j] = 第 i 个化合物在 R[j] 位置的取代基 SMILES
    compounds: list[dict[str, Any]]
    unmatched_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "core_smiles": self.core_smiles,
            "r_labels": self.r_labels,
            "rows": self.rows,
            "compounds": self.compounds,
            "unmatched_count": self.unmatched_count,
        }


@dataclass
class ActivityHeatmap:
    """R-group 取代基 × 活性的热力图数据.

    Attributes:
        r_label: 取代基标签（如 "R1"）
        cells: [{substituent_smiles, avg_activity, count, min, max}]
    """

    r_label: str
    cells: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _strip_esmiles_tags(smiles: str) -> str:
    """剥离 E-SMILES 中的语义标签 (<c>1:R1</c> 等)，保留纯 SMILES。"""
    return _ESMILES_TAG_RE.sub("", smiles)


def _to_mol(smiles: str):
    """解析 SMILES 为 RDKit Mol，失败返回 None。"""
    if not _RDKIT_AVAILABLE:
        return None
    cleaned = _strip_esmiles_tags(smiles)
    try:
        return Chem.MolFromSmiles(cleaned)
    except Exception:
        return None


def _canonical_smiles(smiles: str) -> str:
    """规范化 SMILES（用于比较相等性），失败返回原串。"""
    mol = _to_mol(smiles)
    if mol is None:
        return smiles
    try:
        return Chem.MolToSmiles(mol)
    except Exception:
        return smiles


# ---------------------------------------------------------------------------
# 共同骨架提取
# ---------------------------------------------------------------------------


def find_common_scaffold(
    smiles_list: list[str],
    timeout: float = 5.0,
    min_atoms: int = 3,
) -> str | None:
    """从一组 SMILES 中找最大公共子结构 (MCS) 作为共同骨架.

    Args:
        smiles_list: 化合物 SMILES 列表
        timeout: MCS 搜索超时（秒）
        min_atoms: 骨架最少原子数（小于此值返回 None）

    Returns:
        骨架 SMILES，若无法提取或原子数过少则返回 None
    """
    if not _RDKIT_AVAILABLE or not smiles_list:
        return None

    mols = []
    for s in smiles_list:
        m = _to_mol(s)
        if m is not None:
            mols.append(m)

    if len(mols) < 2:
        return None

    try:
        # RDKit 2026.03: FindMCS 使用位置参数,keyword 参数名已变更
        mcs_result = rdFMCS.FindMCS(
            mols,
            True,  # maximizeBonds
            1.0,  # threshold
            int(timeout),  # timeout (unsigned int)
            False,  # verbose
            False,  # matchValences
            True,  # ringMatchesRingOnly
            True,  # completeRingsOnly
        )
        if mcs_result is None or not mcs_result.smartsString:
            return None
        scaffold_mol = Chem.MolFromSmarts(mcs_result.smartsString)
        if scaffold_mol is None or scaffold_mol.GetNumAtoms() < min_atoms:
            return None
        return Chem.MolToSmiles(scaffold_mol)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# R-group 分解
# ---------------------------------------------------------------------------


def decompose_compound(
    smiles: str,
    core_smiles: str,
    compound_id: str = "",
    compound_name: str = "",
) -> RGroupDecomposition:
    """将单个化合物分解为共同骨架 + R-group 取代基.

    策略：
    1. 在化合物中寻找 core_smarts 的子结构匹配
    2. 未参与匹配的原子 = 取代基
    3. 按连接位置归类，R-label 由位置索引生成 (R1, R2, ...)

    Args:
        smiles: 化合物 SMILES
        core_smiles: 共同骨架 SMILES
        compound_id: 化合物 ID
        compound_name: 化合物名称

    Returns:
        RGroupDecomposition; 若无法匹配则 core_matches=False
    """
    result = RGroupDecomposition(
        compound_id=compound_id,
        compound_name=compound_name,
        smiles=smiles,
        core_matches=False,
    )

    if not _RDKIT_AVAILABLE:
        return result

    mol = _to_mol(smiles)
    if mol is None:
        return result

    core_mol = _to_mol(core_smiles)
    if core_mol is None:
        return result

    try:
        match = mol.GetSubstructMatch(core_mol)
    except Exception:
        return result

    if not match:
        return result

    result.core_matches = True
    core_atom_indices = set(match)

    # 遍历骨架原子，识别每个骨架位置上的外接基团
    # 同一位置的多个外接基团合并为单个取代基
    position_substituents: dict[int, list[int]] = {}
    for core_idx, mol_idx in enumerate(match):
        external_atoms: list[int] = []
        atom = mol.GetAtomWithIdx(mol_idx)
        for neighbor in atom.GetNeighbors():
            n_idx = neighbor.GetIdx()
            if n_idx not in core_atom_indices:
                external_atoms.append(n_idx)
        if external_atoms:
            position_substituents[core_idx] = external_atoms

    # 替换所有骨架原子为 dummy (原子序数 0)，外接基团原子保留
    rw_mol = Chem.RWMol(mol)
    # 替换所有骨架原子为 dummy (原子序数 0)
    dummy_indices: list[int] = []
    for mol_idx in match:
        atom = rw_mol.GetAtomWithIdx(mol_idx)
        atom.SetAtomicNum(0)
        atom.SetFormalCharge(0)
        atom.SetNumExplicitHs(0)
        dummy_indices.append(mol_idx)

    # 删除所有 dummy 原子，R-group 自动断开
    # 按索引降序删除避免索引错乱
    for idx in sorted(dummy_indices, reverse=True):
        rw_mol.RemoveAtom(idx)

    try:
        decomposed_smiles = Chem.MolToSmiles(rw_mol, canonical=False)
    except Exception:
        return result

    # 拆分分解后的 SMILES（多个取代基以 "." 分隔）
    fragments = decomposed_smiles.split(".")

    # 按出现位置归类到 R-label
    # 简化策略：按 fragments 顺序映射到 R1, R2, ...
    # （更精确的算法需要追踪每个 fragment 对应的骨架位置，但同位置多取代基场景少见）
    sorted_positions = sorted(position_substituents.keys())
    if len(fragments) != len(sorted_positions):
        # 数量不匹配可能是 R-group 有环连接 — 退化为整体保留
        if len(fragments) == 1:
            fragments = [decomposed_smiles] * max(1, len(sorted_positions))
        else:
            # 数量偏差超过 1：保守处理，标为未分解
            return result

    for r_idx, (core_idx, fragment) in enumerate(
        zip(sorted_positions, fragments, strict=True)
    ):
        if not fragment or fragment in ("[*]", "[*]"):
            continue
        label = f"R{r_idx + 1}"
        frag_mol = _to_mol(fragment)
        atom_count = frag_mol.GetNumAtoms() if frag_mol is not None else 0
        result.r_groups.append(
            RGroupEntry(
                position=core_idx,
                label=label,
                substituent_smiles=_canonical_smiles(fragment),
                substituent_atoms=atom_count,
            )
        )
    return result


# ---------------------------------------------------------------------------
# R-group 矩阵
# ---------------------------------------------------------------------------


def build_rgroup_matrix(
    compounds: list[dict[str, Any]],
    core_smiles: str | None = None,
    auto_extract_scaffold: bool = True,
    mcs_timeout: float = 5.0,
) -> RGroupMatrix:
    """构建 R-group 矩阵.

    Args:
        compounds: [{id, name, smiles, activity?, activity_type?, units?}, ...]
        core_smiles: 已知共同骨架（None 时自动提取）
        auto_extract_scaffold: 当 core_smiles 为空时是否自动从 compounds 提取
        mcs_timeout: MCS 搜索超时

    Returns:
        RGroupMatrix; 包含矩阵行列数据和化合物元数据
    """
    if not _RDKIT_AVAILABLE:
        return RGroupMatrix(
            core_smiles=core_smiles or "",
            r_labels=[],
            rows=[],
            compounds=list(compounds),
            unmatched_count=len(compounds),
        )

    smiles_list = [c.get("smiles", "") for c in compounds]

    if not core_smiles and auto_extract_scaffold:
        core_smiles = find_common_scaffold(smiles_list, timeout=mcs_timeout)

    if not core_smiles:
        return RGroupMatrix(
            core_smiles="",
            r_labels=[],
            rows=[],
            compounds=list(compounds),
            unmatched_count=len(compounds),
        )

    decompositions = [
        decompose_compound(
            c.get("smiles", ""),
            core_smiles,
            compound_id=c.get("id", ""),
            compound_name=c.get("name", ""),
        )
        for c in compounds
    ]

    # 收集所有 R-label
    all_labels: set[str] = set()
    for d in decompositions:
        for r in d.r_groups:
            all_labels.add(r.label)
    r_labels = sorted(all_labels, key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)

    # 构建矩阵行
    rows: list[list[str]] = []
    matched_meta: list[dict[str, Any]] = []
    unmatched_count = 0

    for d, c in zip(decompositions, compounds, strict=True):
        if not d.core_matches:
            rows.append(["—"] * len(r_labels))
            matched_meta.append({**c, "matches": False})
            unmatched_count += 1
            continue
        rmap = {r.label: r.substituent_smiles for r in d.r_groups}
        row = [rmap.get(label, "—") for label in r_labels]
        rows.append(row)
        matched_meta.append({**c, "matches": True})

    return RGroupMatrix(
        core_smiles=core_smiles,
        r_labels=r_labels,
        rows=rows,
        compounds=matched_meta,
        unmatched_count=unmatched_count,
    )


# ---------------------------------------------------------------------------
# 活性热力图
# ---------------------------------------------------------------------------


def build_activity_heatmap(
    matrix: RGroupMatrix,
    lower_is_better: bool = True,
) -> list[ActivityHeatmap]:
    """基于 R-group 矩阵 + 活性数据构建热力图.

    策略：对每个 R 位置，按取代基 SMILES 分组聚合活性 (mean, min, max, count)。

    Args:
        matrix: 已构建的 R-group 矩阵
        lower_is_better: 活性是否越低越好 (IC50/Ki 为 True，%inhibition 为 False)

    Returns:
        长度为 len(r_labels) 的热力图列表
    """
    heatmaps: list[ActivityHeatmap] = []

    for col_idx, r_label in enumerate(matrix.r_labels):
        # 按取代基 SMILES 聚合活性
        bucket: dict[str, list[float]] = {}
        for row_idx, row in enumerate(matrix.rows):
            if col_idx >= len(row):
                continue
            sub = row[col_idx]
            if sub in ("—", "", None):
                continue
            activity = matrix.compounds[row_idx].get("activity")
            if activity is None:
                continue
            try:
                act_val = float(activity)
            except (TypeError, ValueError):
                continue
            bucket.setdefault(sub, []).append(act_val)

        # 计算每个 bucket 的统计量
        cells: list[dict[str, Any]] = []
        for sub_smiles, values in bucket.items():
            cells.append(
                {
                    "substituent_smiles": sub_smiles,
                    "avg_activity": sum(values) / len(values),
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                }
            )

        # 排序：活性优者排前
        cells.sort(key=lambda c: c["avg_activity"], reverse=not lower_is_better)
        heatmaps.append(ActivityHeatmap(r_label=r_label, cells=cells))

    return heatmaps


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------


def is_available() -> bool:
    """RDKit 是否可用."""
    return _RDKIT_AVAILABLE
