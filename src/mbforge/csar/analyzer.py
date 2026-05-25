"""SAR (结构-活性关系) 分析模块.

本模块提供结构-活性关系分析功能，用于理解分子结构如何影响生物活性。

SAR分析的核心思想:
    通过比较结构相似的分子及其活性差异，识别影响活性的关键结构特征。
    这有助于指导新药设计，优化先导化合物的活性。

分析方法:
    1. 聚类活性统计: 计算每个聚类的活性均值、标准差、最大值、最小值
    2. 子结构贡献分析: 分析MCS骨架上不同取代基对活性的影响
    3. 侧链识别: 识别MCS之外的侧链原子

主要组件:
    - SARAnalyzer: SAR分析器主类
    - SARResult: SAR分析结果数据类
    - SARError: SAR分析异常类

示例:
    >>> analyzer = SARAnalyzer()
    >>> results = analyzer.analyze_clusters(clusters, mcs_results)
    >>> stats = analyzer.get_activity_stats(results)
    >>> print(f"总体平均活性: {stats['mean']:.2f} nM")
"""

from __future__ import annotations

import logging
from typing import Any
from dataclasses import dataclass
from collections import defaultdict

import numpy as np
from rdkit import Chem

from ..clustering.mcs_finder import MCSResult

logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器


class SARError(Exception):
    """SAR分析失败异常.

    当SAR分析过程失败时抛出此异常。
    """

    pass


@dataclass
class SARResult:
    """SAR分析结果数据类.

    存储单个聚类的SAR分析结果。

    属性:
        cluster_id: 聚类ID
        mcs: 该聚类的MCS结果(如果有)
        activities: 聚类中所有分子的活性值列表
        mean_activity: 平均活性
        std_activity: 活性标准差
        max_activity: 最大活性(最低IC50)
        min_activity: 最小活性(最高IC50)
        num_compounds: 聚类中的化合物数量
        contributions: 子结构贡献字典
    """

    cluster_id: int  # 聚类ID
    mcs: MCSResult | None  # MCS结果
    activities: list[float]  # 活性值列表
    mean_activity: float  # 平均活性
    std_activity: float  # 标准差
    max_activity: float  # 最大活性
    min_activity: float  # 最小活性
    num_compounds: int  # 化合物数量
    contributions: dict[str, float]  # 贡献字典


class SARAnalyzer:
    """SAR分析器 - 分析分子聚类中的结构-活性关系.

    该类分析分子聚类中的活性分布，并识别影响活性的结构特征。

    属性:
        activity_threshold: 活性分类阈值(可选)
        use_mcs: 是否使用MCS进行骨架分析

    示例:
        >>> analyzer = SARAnalyzer(activity_threshold=100.0)
        >>> results = analyzer.analyze_clusters(clusters, mcs_results)
        >>> for cid, result in results.items():
        ...     print(f"聚类 {cid}: {result.num_compounds} 个化合物")
        ...     print(f"  平均活性: {result.mean_activity:.2f} ± {result.std_activity:.2f} nM")
    """

    def __init__(
        self, activity_threshold: float | None = None, use_mcs: bool = True
    ) -> None:
        """初始化SAR分析器.

        Args:
            activity_threshold: 活性分类阈值(可选)，用于区分高/低活性.
            use_mcs: 是否使用MCS进行骨架分析，默认为True.
        """
        self.activity_threshold = activity_threshold
        self.use_mcs = use_mcs

    def analyze_cluster(
        self,
        cluster_id: int,
        molecules: list[dict[str, Any]],
        mcs_result: MCSResult | None = None,
    ) -> SARResult:
        """分析单个聚类的SAR.

        计算聚类的活性统计信息，并分析子结构对活性的贡献。

        Args:
            cluster_id: 聚类标识符.
            molecules: 分子字典列表，需包含'mol', 'smiles', 'activity'.
            mcs_result: 该聚类的MCS结果(可选).

        Returns:
            SARResult对象，包含分析详情.
        """
        # 提取所有活性值
        activities = [m["activity"] for m in molecules if "activity" in m]

        # 如果没有活性数据，返回空结果
        if not activities:
            logger.warning(f"聚类 {cluster_id} 没有活性数据")
            return SARResult(
                cluster_id=cluster_id,
                mcs=mcs_result,
                activities=[],
                mean_activity=0.0,
                std_activity=0.0,
                max_activity=0.0,
                min_activity=0.0,
                num_compounds=len(molecules),
                contributions={},
            )

        # 计算活性统计量
        mean_activity = float(np.mean(activities))
        std_activity = float(np.std(activities))
        max_activity = float(np.max(activities))
        min_activity = float(np.min(activities))

        # 分析子结构贡献
        contributions = self._analyze_contributions(molecules, mcs_result)

        return SARResult(
            cluster_id=cluster_id,
            mcs=mcs_result,
            activities=activities,
            mean_activity=mean_activity,
            std_activity=std_activity,
            max_activity=max_activity,
            min_activity=min_activity,
            num_compounds=len(molecules),
            contributions=contributions,
        )

    def _analyze_contributions(
        self, molecules: list[dict[str, Any]], mcs_result: MCSResult | None
    ) -> dict[str, float]:
        """分析子结构对活性的贡献.

        识别MCS骨架上的取代基，并分析不同取代基对活性的影响。

        Args:
            molecules: 分子字典列表.
            mcs_result: MCS结果(可选).

        Returns:
            贡献字典，键为取代基类型，值为平均活性.
        """
        contributions: dict[str, float] = {}

        if mcs_result is None:
            return contributions

        mcs_mol = mcs_result.mcs_mol

        for mol_data in molecules:
            if "activity" not in mol_data:
                continue

            mol = mol_data["mol"]
            activity = mol_data["activity"]

            if not mol.HasSubstructMatch(mcs_mol):
                continue

            side_chains = self._get_side_chains(mol, mcs_mol)

            for atom_idx, _ in side_chains.items():
                atom_symbol = mol.GetAtomWithIdx(atom_idx).GetSymbol()
                key = f"substituent_{atom_symbol}"
                if key not in contributions:
                    contributions[key] = []
                contributions[key].append(activity)

        avg_contributions: dict[str, float] = {}
        for key, values in contributions.items():
            avg_contributions[key] = float(np.mean(values))

        return avg_contributions

    def _get_side_chains(
        self, mol: Chem.Mol, mcs_mol: Chem.Mol
    ) -> dict[int, list[int]]:
        """获取不在MCS中的侧链原子.

        识别连接到MCS骨架但不属于MCS的原子。

        Args:
            mol: 完整分子对象.
            mcs_mol: MCS分子对象(骨架).

        Returns:
            字典，键为MCS原子索引，值为连接的侧链原子索引列表.
        """
        side_chains: dict[int, list[int]] = defaultdict(list)

        mcs_match = mol.GetSubstructMatch(mcs_mol)
        if not mcs_match:
            return side_chains

        mcs_atom_set = set(mcs_match)

        for mcs_atom_idx in range(mcs_mol.GetNumAtoms()):
            mol_atom_idx = mcs_match[mcs_atom_idx]
            mol_atom = mol.GetAtomWithIdx(mol_atom_idx)

            for neighbor in mol_atom.GetNeighbors():
                neighbor_idx = neighbor.GetIdx()
                if neighbor_idx not in mcs_atom_set:
                    side_chains[mol_atom_idx].append(neighbor_idx)

        return side_chains

    def analyze_clusters(
        self, clusters: list[Any], mcs_results: dict[int, MCSResult] | None = None
    ) -> dict[int, SARResult]:
        """分析所有聚类的SAR.

        批量处理多个聚类，为每个聚类执行SAR分析。

        Args:
            clusters: 聚类对象列表.
            mcs_results: MCS结果字典，键为cluster_id(可选).

        Returns:
            字典，键为cluster_id，值为SARResult.
        """
        results: dict[int, SARResult] = {}
        mcs_map = mcs_results or {}

        for cluster in clusters:
            cluster_id = (
                cluster.cluster_id
                if hasattr(cluster, "cluster_id")
                else cluster.get("cluster_id", 0)
            )
            molecules = (
                cluster.molecules
                if hasattr(cluster, "molecules")
                else cluster.get("molecules", [])
            )

            logger.info(f"Analyzing SAR for cluster {cluster_id}")

            mcs_result = mcs_map.get(cluster_id)

            try:
                sar_result = self.analyze_cluster(cluster_id, molecules, mcs_result)
                results[cluster_id] = sar_result
            except Exception as e:
                logger.warning(f"Failed to analyze cluster {cluster_id}: {e}")

        return results

    def get_activity_stats(self, sar_results: dict[int, SARResult]) -> dict[str, float]:
        """获取跨聚类的总体活性统计.

        汇总所有聚类的活性数据，计算总体统计量。

        Args:
            sar_results: SAR结果字典，键为cluster_id.

        Returns:
            统计字典，包含mean, std, max, min, total_compounds.
        """
        all_activities = []
        for result in sar_results.values():
            all_activities.extend(result.activities)

        if not all_activities:
            return {
                "mean": 0.0,
                "std": 0.0,
                "max": 0.0,
                "min": 0.0,
                "total_compounds": 0,
            }

        return {
            "mean": float(np.mean(all_activities)),
            "std": float(np.std(all_activities)),
            "max": float(np.max(all_activities)),
            "min": float(np.min(all_activities)),
            "total_compounds": len(all_activities),
        }


# ---- CLI 入口 ----

if __name__ == "__main__":
    import argparse
    import json
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(description="MBForge SAR 分析工具")
    parser.add_argument("input", help="分子文件路径 (SDF/CSV/SMILES)")
    parser.add_argument("--smiles-column", default="SMILES", help="CSV 中 SMILES 列名")
    parser.add_argument(
        "--activity-column", default="activity", help="CSV 中活性值列名"
    )
    parser.add_argument("--threshold", type=float, default=None, help="活性阈值")
    parser.add_argument("--output", "-o", default=None, help="输出 JSON 文件路径")
    args = parser.parse_args()

    from ..molecules.loader import load_molecules_from_file

    molecules = load_molecules_from_file(
        args.input, args.smiles_column, args.activity_column
    )
    print(f"Loaded {len(molecules)} molecules")

    # 检查是否有活性数据
    with_activity = [m for m in molecules if "activity" in m]
    if not with_activity:
        print(
            "Error: No activity data found. Use --activity-column to specify.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 作为单个大簇分析
    analyzer = SARAnalyzer(activity_threshold=args.threshold)
    result = analyzer.analyze_cluster(cluster_id=0, molecules=with_activity)

    output_data = {
        "cluster_id": result.cluster_id,
        "num_compounds": result.num_compounds,
        "mean_activity": round(result.mean_activity, 4),
        "std_activity": round(result.std_activity, 4),
        "max_activity": round(result.max_activity, 4),
        "min_activity": round(result.min_activity, 4),
        "contributions": result.contributions,
    }

    output = json.dumps(output_data, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Saved SAR result to {args.output}")
    else:
        print(output)
