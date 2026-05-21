"""最大公共子结构(MCS)查找模块.

本模块提供查找分子间最大公共子结构的功能。
MCS是多个分子共有的最大结构片段，用于识别共同的结构骨架。

主要功能:
    - MCS查找: 在多个分子间查找最大公共子结构
    - 取代位点识别: 识别MCS骨架上的R基团位置
    - 骨架标记: 生成带R标签的骨架图像

主要类:
    MCSFinder: MCS查找器，支持多分子和超时控制
    MCSResult: MCS查找结果数据类
    ScaffoldInfo: 骨架信息，包含R基团位置
    SubstituentInfo: 取代基信息

示例:
    >>> from mbforge.mcs import MCSFinder
    >>> finder = MCSFinder(timeout=30)
    >>> result = finder.find_mcs(molecules)
    >>> print(f"MCS包含 {result.num_atoms} 个原子")
"""

# 从子模块导入主要类和异常
from .finder import MCSFinder, MCSError, MCSResult  # MCS查找器、异常和结果类

# 模块公开接口
__all__ = [
    "MCSFinder",  # MCS查找器
    "MCSError",  # MCS查找异常
    "MCSResult",  # MCS结果数据类
]
