"""分子处理核心模块.

本模块提供统一的分子数据模型和高级的分子处理能力，包括：
- 标准化分子数据模型 (Molecule)
- 分子描述符计算
- 分子过滤与筛选
- 分子标准化与预处理
- 骨架与片段分析
- 子结构匹配与 SMARTS 查询

示例:
    >>> from mbforge.molecules import Molecule, MoleculeDescriptorCalculator
    >>> mol = Molecule.from_smiles("CCO", name="Ethanol")
    >>> calc = MoleculeDescriptorCalculator()
    >>> desc = calc.compute(mol.mol)
    >>> print(desc.molecular_weight)
"""

from __future__ import annotations

from .schema import Molecule, MoleculeBatch, MoleculeEntry
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
    # 数据模型（schema.py — 唯一契约）
    "Molecule",
    "MoleculeBatch",
    "MoleculeEntry",  # 兼容别名，指向 Molecule
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
