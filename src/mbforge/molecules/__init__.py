"""分子处理核心模块.

本模块提供统一的分子数据模型和高级的分子处理能力，包括：
- 标准化分子数据模型 (MoleculeEntry)
- 分子描述符计算
- 分子过滤与筛选
- 分子标准化与预处理
- 骨架与片段分析
- 子结构匹配与 SMARTS 查询

示例:
    >>> from mbforge.molecules import MoleculeEntry, MoleculeDescriptorCalculator
    >>> entry = MoleculeEntry.from_smiles("CCO", name="Ethanol")
    >>> calc = MoleculeDescriptorCalculator()
    >>> desc = calc.compute(entry.mol)
    >>> print(desc.molecular_weight)
"""

from __future__ import annotations

from .models import MoleculeEntry, MoleculeBatch
from .descriptors import (
    MoleculeDescriptorCalculator,
    DescriptorSet,
)
from .filters import (
    MoleculeFilter,
    LipinskiFilter,
    VeberFilter,
    PAINSFilter,
    CompositeFilter,
)
from .standardizer import MoleculeStandardizer
from .fragment import (
    ScaffoldAnalyzer,
    RECAPFragmenter,
    BRICSFragmenter,
)
from .matcher import (
    SubstructureMatcher,
    SMARTSQuery,
)

__all__ = [
    # 数据模型
    "MoleculeEntry",
    "MoleculeBatch",
    # 描述符
    "MoleculeDescriptorCalculator",
    "DescriptorSet",
    # 过滤器
    "MoleculeFilter",
    "LipinskiFilter",
    "VeberFilter",
    "PAINSFilter",
    "CompositeFilter",
    # 标准化
    "MoleculeStandardizer",
    # 片段分析
    "ScaffoldAnalyzer",
    "RECAPFragmenter",
    "BRICSFragmenter",
    # 子结构匹配
    "SubstructureMatcher",
    "SMARTSQuery",
]
