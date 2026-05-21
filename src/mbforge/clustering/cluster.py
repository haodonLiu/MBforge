"""分子聚类算法模块.

本模块提供基于分子指纹相似性的聚类算法。
聚类将相似的分子分组，有助于发现结构相似的化合物系列。

支持的聚类算法:
    - Tanimoto聚类: 基于Tanimoto相似度阈值的简单聚类
    - Butina聚类: RDKit实现的Butina聚类算法，产生更紧凑的聚类

聚类结果:
    每个聚类包含:
    - cluster_id: 聚类ID
    - molecules: 聚类中的分子列表
    - representative_idx: 代表性分子的索引
    - size: 聚类大小
    - avg_similarity: 平均相似度

示例:
    >>> from mbforge.clustering import MolecularClusterer, MolecularFingerprinter
    >>> fingerprinter = MolecularFingerprinter()
    >>> clusterer = MolecularClusterer(fingerprinter, threshold=0.7)
    >>> clusters = clusterer.cluster(molecules)
    >>> print(f"发现 {len(clusters)} 个聚类")
"""

from __future__ import annotations

import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

import numpy as np
from rdkit import Chem
from rdkit.ML.Cluster import Butina

from .fingerprinter import MolecularFingerprinter

logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器


class ClusteringError(Exception):
    """聚类操作失败异常.
    
    当分子聚类过程失败时抛出此异常。
    """

    pass


@dataclass
class ClusterResult:
    """聚类操作结果数据类.
    
    存储单个聚类的详细信息。
    
    属性:
        cluster_id: 聚类唯一标识符
        molecules: 聚类中包含的分子字典列表
        representative_idx: 代表性分子在列表中的索引
        size: 聚类中分子的数量
        avg_similarity: 聚类内分子的平均相似度
    """

    cluster_id: int  # 聚类ID
    molecules: List[Dict[str, object]]  # 分子列表
    representative_idx: int  # 代表性分子索引
    size: int  # 聚类大小
    avg_similarity: float = 0.0  # 平均相似度


class MolecularClusterer:
    """分子聚类器 - 基于指纹相似性.
    
    该类使用分子指纹相似性将分子分组为聚类。
    支持Tanimoto和Butina两种聚类算法。
    
    属性:
        fingerprinter: 分子指纹计算器实例
        threshold: 相似度阈值 (0.0-1.0)
        method: 聚类方法 ("tanimoto" 或 "butina")
    
    示例:
        >>> clusterer = MolecularClusterer(threshold=0.7, method="butina")
        >>> clusters = clusterer.cluster(molecules)
        >>> for cluster in clusters:
        ...     print(f"聚类 {cluster.cluster_id}: {cluster.size} 个分子")
    """

    def __init__(
        self,
        fingerprinter: Optional[MolecularFingerprinter] = None,
        threshold: float = 0.7,
        method: str = "tanimoto",
    ) -> None:
        """初始化分子聚类器.

        Args:
            fingerprinter: 分子指纹计算器实例，默认创建新的实例.
            threshold: 聚类相似度阈值 (0.0-1.0)，默认为0.7.
            method: 聚类方法，可选"tanimoto"(默认)或"butina".
        """
        self.fingerprinter = fingerprinter or MolecularFingerprinter()
        self.threshold = threshold
        self.method = method

    def cluster(self, molecules: List[Dict[str, object]]) -> Tuple[List[ClusterResult], np.ndarray]:
        """基于指纹相似性对分子进行聚类.

        Args:
            molecules: 分子字典列表，每个字典必须包含'mol'键(RDKit分子对象).

        Returns:
            Tuple of (ClusterResult列表, 相似度矩阵).

        Raises:
            ClusteringError: 聚类失败时抛出.
        """
        if len(molecules) == 0:
            return [], np.array([])

        logger.info(f"Clustering {len(molecules)} molecules, threshold={self.threshold}")

        try:
            if self.method == "butina":
                return self._cluster_butina(molecules)
            else:
                return self._cluster_tanimoto(molecules)
        except Exception as e:
            raise ClusteringError(f"Clustering failed: {e}") from e

    def _cluster_butina(
        self, molecules: List[Dict[str, object]]
    ) -> Tuple[List[ClusterResult], np.ndarray]:
        """使用Butina算法进行聚类.
        
        Butina算法是一种基于距离矩阵的聚类方法，
        首先选择相似度最高的分子作为聚类中心，
        然后将相似度高于阈值的分子分配到该聚类。
        
        Args:
            molecules: 分子字典列表.

        Returns:
            Tuple of (ClusterResult列表, 相似度矩阵).
        """
        fps = [self.fingerprinter.fingerprint(m["mol"]).fingerprint for m in molecules]
        n = len(fps)

        distance_matrix = np.zeros((n, n), dtype=np.float64)
        for i in range(n):
            for j in range(i + 1, n):
                sim = self.fingerprinter._tanimoto(fps[i], fps[j])
                distance_matrix[i, j] = 1.0 - sim
                distance_matrix[j, i] = 1.0 - sim

        cluster_ids = Butina.ClusterData(
            distance_matrix, n, self.threshold, isDistData=True
        )

        results: List[ClusterResult] = []
        for cluster_id, indices in enumerate(cluster_ids):
            if len(indices) == 0:
                continue

            cluster_mols = [molecules[i] for i in indices]

            dists = (
                [distance_matrix[indices[0]][i] for i in indices[1:]]
                if len(indices) > 1
                else [0.0]
            )
            avg_sim = 1.0 - np.mean(dists) if dists else 1.0

            results.append(
                ClusterResult(
                    cluster_id=cluster_id,
                    molecules=cluster_mols,
                    representative_idx=indices[0],
                    size=len(indices),
                    avg_similarity=avg_sim,
                )
            )

        # Convert distance matrix to similarity matrix
        sim_matrix = np.ones((n, n), dtype=np.float64)
        for i in range(n):
            for j in range(n):
                sim_matrix[i, j] = 1.0 - distance_matrix[i, j]

        logger.info(f"Found {len(results)} clusters")
        return results, sim_matrix

    def _cluster_tanimoto(
        self, molecules: List[Dict[str, object]]
    ) -> Tuple[List[ClusterResult], np.ndarray]:
        """使用Tanimoto相似度阈值进行聚类.

        简单的贪心聚类算法:
        1. 选择第一个未分配的分子作为新聚类的中心
        2. 将所有相似度高于阈值的未分配分子加入该聚类
        3. 重复直到所有分子都被分配

        Args:
            molecules: 分子字典列表.

        Returns:
            Tuple of (ClusterResult列表, 相似度矩阵).
        """
        sim_matrix = self.fingerprinter.pairwise_similarity(
            [m["mol"] for m in molecules]
        )

        n = len(molecules)
        assigned = [False] * n
        results: List[ClusterResult] = []

        for i in range(n):
            if assigned[i]:
                continue

            indices = [i]
            assigned[i] = True

            for j in range(i + 1, n):
                if not assigned[j] and sim_matrix[i, j] >= self.threshold:
                    indices.append(j)
                    assigned[j] = True

            cluster_mols = [molecules[idx] for idx in indices]

            row_sims = [sim_matrix[i][j] for j in indices if j != i]
            avg_sim = np.mean(row_sims) if len(row_sims) > 0 else 1.0

            results.append(
                ClusterResult(
                    cluster_id=len(results),
                    molecules=cluster_mols,
                    representative_idx=i,
                    size=len(indices),
                    avg_similarity=avg_sim,
                )
            )

        logger.info(f"Found {len(results)} clusters")
        return results, sim_matrix
