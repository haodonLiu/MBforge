"""Bemis-Murcko 骨架聚类模块.

基于 Bemis-Murcko 骨架 (通用骨架) 对分子进行聚类。
与基于指纹相似度的聚类不同，骨架聚类关注分子的核心结构特征，
适用于 SAR 分析中按骨架系列组织化合物。

功能:
    - Murcko 骨架提取: 从分子中提取 Bemis-Murcko 通用骨架
    - 骨架聚类: 将具有相同或相似骨架的分子分组
    - 骨架统计: 计算每个骨架簇的活性统计
    - 骨架可视化: 生成骨架图像用于报告

Bemis-Murcko 骨架定义:
    分子的环系统和连接环的键，去掉所有侧链取代基。
    例如: 苯环 + 连接键 = c1ccccc1 (苯基骨架)

参考:
    Bemis, G.W. & Murcko, M.A. (1996).
    "The Properties of Known Drugs. 1. Molecular Frameworks."
    J. Med. Chem. 39, 2887-2893.

示例:
    >>> from mbforge.clustering.scaffold import ScaffoldClusterer, get_murcko_scaffold
    >>> scaffold = get_murcko_scaffold(mol)
    >>> clusterer = ScaffoldClusterer()
    >>> clusters = clusterer.cluster(molecules)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from rdkit import Chem
from rdkit.Chem.Scaffolds import MurckoScaffold

logger = logging.getLogger(__name__)


class ScaffoldClusteringError(Exception):
    """骨架聚类操作失败."""

    pass


def get_murcko_scaffold(
    mol: Chem.Mol,
    include_chirality: bool = False,
) -> Optional[Chem.Mol]:
    """提取分子的 Bemis-Murcko 通用骨架.

    Args:
        mol: RDKit 分子对象.
        include_chirality: 是否保留手性信息.

    Returns:
        骨架分子对象; 如果无法提取则返回 None.
    """
    if mol is None:
        return None

    try:
        scaffold = MurckoScaffold.GetScaffoldForMol(mol)
        if scaffold is None or scaffold.GetNumAtoms() == 0:
            return None

        # 转换为 SMILES 再转回，标准化表示
        scaffold_smiles = Chem.MolToSmiles(scaffold, include_chirality=include_chirality)
        if not scaffold_smiles or scaffold_smiles == "":
            return None

        scaffold_mol = Chem.MolFromSmiles(scaffold_smiles)
        return scaffold_mol

    except Exception as e:
        logger.warning(f"Failed to extract Murcko scaffold: {e}")
        return None


def get_murcko_scaffold_smiles(
    mol: Chem.Mol,
    include_chirality: bool = False,
) -> str:
    """提取分子的 Bemis-Murcko 骨架 SMILES.

    Args:
        mol: RDKit 分子对象.
        include_chirality: 是否保留手性信息.

    Returns:
        骨架 SMILES 字符串; 失败返回空字符串.
    """
    scaffold = get_murcko_scaffold(mol, include_chirality=include_chirality)
    if scaffold is None:
        return ""
    return Chem.MolToSmiles(scaffold)


class ScaffoldClusterResult:
    """骨架聚类结果.

    Attributes:
        scaffold_smiles: 骨架 SMILES.
        scaffold_mol: 骨架分子对象.
        molecules: 属于该骨架的分子列表.
        num_molecules: 分子数量.
        activities: 活性值列表.
        mean_activity: 平均活性值.
        min_activity: 最小活性值 (最高活性).
        max_activity: 最大活性值 (最低活性).
    """

    def __init__(
        self,
        scaffold_smiles: str,
        scaffold_mol: Optional[Chem.Mol],
        molecules: List[Dict[str, Any]],
    ) -> None:
        self.scaffold_smiles = scaffold_smiles
        self.scaffold_mol = scaffold_mol
        self.molecules = molecules
        self.num_molecules = len(molecules)

        # 提取活性值
        self.activities: List[float] = []
        for mol_dict in molecules:
            activity = mol_dict.get("activity")
            if activity is not None and isinstance(activity, (int, float)):
                self.activities.append(float(activity))

        # 统计
        if self.activities:
            self.mean_activity = sum(self.activities) / len(self.activities)
            self.min_activity = min(self.activities)  # IC50: 越小越强
            self.max_activity = max(self.activities)
        else:
            self.mean_activity = 0.0
            self.min_activity = 0.0
            self.max_activity = 0.0

    def __repr__(self) -> str:
        return (
            f"ScaffoldClusterResult("
            f"scaffold='{self.scaffold_smiles}', "
            f"n={self.num_molecules}, "
            f"mean_act={self.mean_activity:.2f})"
        )


class ScaffoldClusterer:
    """基于 Bemis-Murcko 骨架的分子聚类器.

    将分子按其 Bemis-Murcko 骨架进行聚类。相同骨架的分子归为一组。
    可选地合并仅因 aromatic/kekulize 差异而不同的骨架。

    Attributes:
        include_chirality: 是否在手性层面区分骨架.
        merge_aromatic_kekulize: 是否合并芳香性/Kekulé 差异.
        min_cluster_size: 返回的最小簇大小.
    """

    def __init__(
        self,
        include_chirality: bool = False,
        merge_aromatic_kekulize: bool = True,
        min_cluster_size: int = 1,
    ) -> None:
        """初始化骨架聚类器.

        Args:
            include_chirality: 是否区分手性骨架.
            merge_aromatic_kekulize: 是否合并芳香性/Kekulé 形式差异.
            min_cluster_size: 返回结果的最小簇大小 (默认 1).
        """
        self.include_chirality = include_chirality
        self.merge_aromatic_kekulize = merge_aromatic_kekulize
        self.min_cluster_size = min_cluster_size

    def _normalize_scaffold_smiles(self, smiles: str) -> str:
        """标准化骨架 SMILES 用于比较.

        如果启用了 merge_aromatic_kekulize，将 SMILES 标准化为
        芳香形式以消除 Kekulé 差异。

        Args:
            smiles: 原始 SMILES.

        Returns:
            标准化后的 SMILES.
        """
        if not smiles or self.merge_aromatic_kekulize is False:
            return smiles

        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return smiles
            # 强制转换为芳香形式再输出
            normalized = Chem.MolToSmiles(mol)
            return normalized
        except Exception:
            return smiles

    def cluster(
        self,
        molecules: List[Dict[str, Any]],
    ) -> List[ScaffoldClusterResult]:
        """根据 Bemis-Murcko 骨架对分子聚类.

        Args:
            molecules: 分子字典列表，每个包含 'mol' 键和其他可选键.

        Returns:
            ScaffoldClusterResult 列表，按分子数量降序排列.

        Raises:
            ScaffoldClusteringError: 输入为空或全部提取失败时抛出.
        """
        if not molecules:
            raise ScaffoldClusteringError("分子列表不能为空")

        # 按骨架分组
        scaffold_groups: Dict[str, List[Dict[str, Any]]] = {}

        for mol_dict in molecules:
            mol = mol_dict.get("mol")
            if mol is None:
                logger.warning(f"Skipping molecule without 'mol': {mol_dict.get('name', '?')}")
                continue

            raw_smiles = get_murcko_scaffold_smiles(
                mol, include_chirality=self.include_chirality
            )
            if not raw_smiles:
                logger.warning(
                    f"Cannot extract scaffold for: {mol_dict.get('name', '?')}"
                )
                continue

            norm_smiles = self._normalize_scaffold_smiles(raw_smiles)

            if norm_smiles not in scaffold_groups:
                scaffold_groups[norm_smiles] = []
            scaffold_groups[norm_smiles].append(mol_dict)

        if not scaffold_groups:
            raise ScaffoldClusteringError("无法从任何分子中提取骨架")

        # 构建结果
        results: List[ScaffoldClusterResult] = []
        for scaffold_smiles, group_mols in scaffold_groups.items():
            if len(group_mols) < self.min_cluster_size:
                continue

            # 使用第一个分子获取 scaffold_mol
            first_mol = group_mols[0].get("mol")
            scaffold_mol = get_murcko_scaffold(
                first_mol, include_chirality=self.include_chirality
            )

            result = ScaffoldClusterResult(
                scaffold_smiles=scaffold_smiles,
                scaffold_mol=scaffold_mol,
                molecules=group_mols,
            )
            results.append(result)

        # 按分子数量降序排列
        results.sort(key=lambda x: x.num_molecules, reverse=True)

        logger.info(
            f"Scaffold clustering completed: "
            f"{len(results)} scaffolds from {len(molecules)} molecules"
        )

        return results

    def get_scaffold_diversity(self, molecules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算数据集的骨架多样性指标.

        Args:
            molecules: 分子字典列表.

        Returns:
            包含多样性统计的字典:
            - total_molecules: 总分子数
            - unique_scaffolds: 唯一骨架数
            - singleton_scaffolds: 只有一个成员的骨架数
            - largest_cluster_size: 最大簇的大小
            - scaffold_diversity_index: 骨架多样性指数 (unique/total)
        """
        results = self.cluster(molecules)

        total = len(molecules)
        unique = len(results)
        singletons = sum(1 for r in results if r.num_molecules == 1)
        largest = max((r.num_molecules for r in results), default=0)
        diversity_index = unique / total if total > 0 else 0.0

        return {
            "total_molecules": total,
            "unique_scaffolds": unique,
            "singleton_scaffolds": singletons,
            "largest_cluster_size": largest,
            "scaffold_diversity_index": round(diversity_index, 4),
        }


# ---- CLI 入口 ----

if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="MBForge 骨架聚类工具")
    parser.add_argument("input", help="分子文件路径 (SDF/CSV/SMILES)")
    parser.add_argument("--min-cluster", type=int, default=1, help="最小簇大小")
    parser.add_argument("--smiles-column", default="SMILES", help="CSV 中 SMILES 列名")
    parser.add_argument("--activity-column", default=None, help="CSV 中活性值列名")
    parser.add_argument("--output", "-o", default=None, help="输出 JSON 文件路径")
    args = parser.parse_args()

    from ..molecules.loader import load_molecules_from_file

    molecules = load_molecules_from_file(args.input, args.smiles_column, args.activity_column)
    print(f"Loaded {len(molecules)} molecules")

    clusterer = ScaffoldClusterer(min_cluster_size=args.min_cluster)
    clusters = clusterer.cluster(molecules)
    diversity = clusterer.get_scaffold_diversity(molecules)

    results = {
        "diversity": diversity,
        "clusters": [],
    }
    for c in clusters:
        results["clusters"].append({
            "scaffold": c.scaffold_smiles,
            "num_molecules": c.num_molecules,
            "mean_activity": round(c.mean_activity, 4) if c.mean_activity is not None else None,
            "smiles": [m.get("smiles", "") for m in c.molecules],
        })

    output = json.dumps(results, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Saved {len(clusters)} scaffold clusters to {args.output}")
    else:
        print(output)
