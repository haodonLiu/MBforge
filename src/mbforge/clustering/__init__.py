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

# 从子模块导入主要类和异常
from .fingerprinter import MolecularFingerprinter  # 分子指纹计算器
from .cluster import MolecularClusterer, ClusteringError  # 分子聚类器和聚类异常
from .scaffold import ScaffoldClusterer, ScaffoldClusteringError  # 骨架聚类器

# 模块公开接口
__all__ = [
    "MolecularFingerprinter",  # 分子指纹计算器
    "MolecularClusterer",  # 分子聚类器 (基于指纹)
    "ClusteringError",  # 聚类异常
    "ScaffoldClusterer",  # 骨架聚类器 (Bemis-Murcko)
    "ScaffoldClusteringError",  # 骨架聚类异常
]
