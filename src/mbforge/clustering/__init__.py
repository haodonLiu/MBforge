"""分子指纹计算、相似性计算和骨架聚类模块.

本模块提供:
    - 分子指纹生成和基于指纹的相似性计算
    - 基于Tanimoto/Butina的分子聚类
    - Bemis-Murcko 骨架聚类

支持的聚类方式:
    - 指纹相似度聚类 (MolecularClusterer)
    - 骨架聚类 (ScaffoldClusterer)

示例:
    >>> from mbforge.clustering import MolecularFingerprinter, MolecularClusterer, ScaffoldClusterer
    >>> fp = MolecularFingerprinter(fp_type="Morgan")
    >>> clusterer = MolecularClusterer(threshold=0.7)
    >>> scaffold_clusterer = ScaffoldClusterer()
"""

from .fingerprinter import MolecularFingerprinter
from .cluster import MolecularClusterer, ClusteringError
from .scaffold import ScaffoldClusterer, ScaffoldClusteringError
from .mcs_finder import MCSFinder, MCSError, MCSResult, MCSScaffoldInfo

__all__ = [
    "MolecularFingerprinter",
    "MolecularClusterer",
    "ClusteringError",
    "ScaffoldClusterer",
    "ScaffoldClusteringError",
    "MCSFinder",
    "MCSError",
    "MCSResult",
    "MCSScaffoldInfo",
]
