"""SAR (Structure-Activity Relationship) 分析工具箱.

子模块：
- sar: 共同骨架提取、R-group 分解、矩阵构建、活性热力图
"""

from __future__ import annotations

from .sar import (
    ActivityHeatmap,
    RGroupDecomposition,
    RGroupEntry,
    RGroupMatrix,
    build_activity_heatmap,
    build_rgroup_matrix,
    decompose_compound,
    find_common_scaffold,
    is_available,
)

__all__ = [
    "ActivityHeatmap",
    "RGroupDecomposition",
    "RGroupEntry",
    "RGroupMatrix",
    "build_activity_heatmap",
    "build_rgroup_matrix",
    "decompose_compound",
    "find_common_scaffold",
    "is_available",
]
