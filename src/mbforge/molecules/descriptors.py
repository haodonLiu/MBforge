"""分子描述符计算模块.

提供全面、可扩展的分子描述符计算能力，涵盖 2D 描述符和基础 3D 描述符。
支持描述符集合管理和批量计算。

核心类:
    MoleculeDescriptorCalculator: 描述符计算器主类
    DescriptorSet: 描述符集合枚举

示例:
    >>> calc = MoleculeDescriptorCalculator(descriptor_set="all_2d")
    >>> desc = calc.compute(mol)
    >>> print(desc["MolWt"], desc["TPSA"])
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
from rdkit import Chem
from rdkit.Chem import Descriptors, GraphDescriptors, MolSurf, Lipinski, rdMolDescriptors
from rdkit.Chem import AllChem, Descriptors3D

logger = logging.getLogger(__name__)


class DescriptorSet(str, Enum):
    """描述符集合枚举.

    预定义常用的描述符组合，方便一键计算。
    """

    BASIC = "basic"  # 基础描述符：分子量、LogP、氢键数等
    LIPINSKI = "lipinski"  # Lipinski 五规则相关描述符
    TOPOLOGICAL = "topological"  # 拓扑描述符
    ELECTRONIC = "electronic"  # 电子相关描述符
    ALL_2D = "all_2d"  # 所有 RDKit 2D 描述符
    MORGAN_FP = "morgan_fp"  # Morgan 指纹相关
    ALL_3D = "all_3d"  # 3D 构象描述符（需先生成构象）
    CUSTOM = "custom"  # 自定义描述符集合


@dataclass
class DescriptorResult:
    """描述符计算结果.

    属性:
        values: 描述符名称 -> 值的字典.
        mol: 原始分子对象.
        success: 是否全部成功计算.
        errors: 计算过程中遇到的错误信息.
    """

    values: Dict[str, Any] = field(default_factory=dict)
    mol: Optional[Chem.Mol] = None
    success: bool = True
    errors: List[str] = field(default_factory=list)

    def get(self, name: str, default: Any = None) -> Any:
        """获取指定描述符值.

        Args:
            name: 描述符名称.
            default: 默认值.

        Returns:
            描述符值或默认值.
        """
        return self.values.get(name, default)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典."""
        return dict(self.values)

    def to_array(self, names: Optional[List[str]] = None) -> np.ndarray:
        """转换为 NumPy 数组.

        Args:
            names: 要包含的描述符名称列表，默认包含所有数值型描述符.

        Returns:
            一维 NumPy 数组.
        """
        if names is None:
            names = [k for k, v in self.values.items() if isinstance(v, (int, float))]
        arr = []
        for name in names:
            v = self.values.get(name)
            if v is None or not isinstance(v, (int, float)):
                arr.append(np.nan)
            else:
                arr.append(float(v))
        return np.array(arr, dtype=float)


class MoleculeDescriptorCalculator:
    """分子描述符计算器.

    支持预定义描述符集合和自定义描述符函数，可批量计算分子描述符。

    属性:
        descriptor_set: 当前使用的描述符集合.
        custom_descriptors: 用户自定义描述符函数字典.
        include_3d: 是否包含 3D 描述符（需先优化构象）.
    """

    # 预定义描述符映射
    _DESCRIPTOR_REGISTRY: Dict[str, List[Tuple[str, Callable]]] = {
        "basic": [
            ("MolWt", Descriptors.MolWt),
            ("MolLogP", Descriptors.MolLogP),
            ("MolMR", Descriptors.MolMR),
            ("TPSA", rdMolDescriptors.CalcTPSA),
            ("NumHBD", rdMolDescriptors.CalcNumHBD),
            ("NumHBA", rdMolDescriptors.CalcNumHBA),
            ("NumRotatableBonds", rdMolDescriptors.CalcNumRotatableBonds),
            ("NumHeavyAtoms", Lipinski.HeavyAtomCount),
            ("NumRings", rdMolDescriptors.CalcNumRings),
            ("NumAromaticRings", rdMolDescriptors.CalcNumAromaticRings),
            ("NumAliphaticRings", rdMolDescriptors.CalcNumAliphaticRings),
            ("NumHeteroatoms", rdMolDescriptors.CalcNumHeteroatoms),
            ("FractionCSP3", rdMolDescriptors.CalcFractionCSP3),
            ("FormalCharge", Descriptors.NumValenceElectrons),  # 替代形式电荷
        ],
        "lipinski": [
            ("MolWt", Descriptors.MolWt),
            ("MolLogP", Descriptors.MolLogP),
            ("NumHBD", rdMolDescriptors.CalcNumHBD),
            ("NumHBA", rdMolDescriptors.CalcNumHBA),
            ("NumRotatableBonds", rdMolDescriptors.CalcNumRotatableBonds),
        ],
        "topological": [
            ("BalabanJ", GraphDescriptors.BalabanJ),
            ("BertzCT", GraphDescriptors.BertzCT),
            ("HallKierAlpha", Descriptors.HallKierAlpha),
            ("Kappa1", Descriptors.Kappa1),
            ("Kappa2", Descriptors.Kappa2),
            ("Kappa3", Descriptors.Kappa3),
            ("Chi0v", Descriptors.Chi0v),
            ("Chi1v", Descriptors.Chi1v),
            ("Chi2v", Descriptors.Chi2v),
            ("Chi3v", Descriptors.Chi3v),
            ("Chi4v", Descriptors.Chi4v),
        ],
        "electronic": [
            ("MaxPartialCharge", Descriptors.MaxPartialCharge),
            ("MinPartialCharge", Descriptors.MinPartialCharge),
            ("MaxAbsPartialCharge", Descriptors.MaxAbsPartialCharge),
            ("MinAbsPartialCharge", Descriptors.MinAbsPartialCharge),
            ("NumRadicalElectrons", Descriptors.NumRadicalElectrons),
        ],
        "morgan_fp": [
            ("MorganFP_2048", lambda m: rdMolDescriptors.GetMorganFingerprintAsBitVect(m, 2, nBits=2048)),
            ("MorganFP_1024", lambda m: rdMolDescriptors.GetMorganFingerprintAsBitVect(m, 2, nBits=1024)),
        ],
    }

    # 2D 描述符白名单（rdMolDescriptors 中常用函数）
    _ALL_2D_DESCRIPTORS: List[Tuple[str, Callable]] = [
        ("MolWt", Descriptors.MolWt),
        ("MolLogP", Descriptors.MolLogP),
        ("MolMR", Descriptors.MolMR),
        ("ExactMolWt", Descriptors.ExactMolWt),
        ("TPSA", rdMolDescriptors.CalcTPSA),
        ("LabuteASA", rdMolDescriptors.CalcLabuteASA),
        ("NumHBD", rdMolDescriptors.CalcNumHBD),
        ("NumHBA", rdMolDescriptors.CalcNumHBA),
        ("NumRotatableBonds", rdMolDescriptors.CalcNumRotatableBonds),
        ("NumHeteroatoms", rdMolDescriptors.CalcNumHeteroatoms),
        ("NumRings", rdMolDescriptors.CalcNumRings),
        ("NumAromaticRings", rdMolDescriptors.CalcNumAromaticRings),
        ("NumAliphaticRings", rdMolDescriptors.CalcNumAliphaticRings),
        ("NumSaturatedRings", rdMolDescriptors.CalcNumSaturatedRings),
        ("NumAromaticHeterocycles", rdMolDescriptors.CalcNumAromaticHeterocycles),
        ("NumAromaticCarbocycles", rdMolDescriptors.CalcNumAromaticCarbocycles),
        ("NumAliphaticHeterocycles", rdMolDescriptors.CalcNumAliphaticHeterocycles),
        ("NumAliphaticCarbocycles", rdMolDescriptors.CalcNumAliphaticCarbocycles),
        ("NumSaturatedHeterocycles", rdMolDescriptors.CalcNumSaturatedHeterocycles),
        ("NumSaturatedCarbocycles", rdMolDescriptors.CalcNumSaturatedCarbocycles),
        ("NumSpiroAtoms", rdMolDescriptors.CalcNumSpiroAtoms),
        ("NumBridgeheadAtoms", rdMolDescriptors.CalcNumBridgeheadAtoms),
        ("NumAmideBonds", rdMolDescriptors.CalcNumAmideBonds),
        ("FractionCSP3", rdMolDescriptors.CalcFractionCSP3),
        ("HeavyAtomMolWt", Descriptors.HeavyAtomMolWt),
        ("NumValenceElectrons", Descriptors.NumValenceElectrons),
        ("NumRadicalElectrons", Descriptors.NumRadicalElectrons),
        ("MaxPartialCharge", Descriptors.MaxPartialCharge),
        ("MinPartialCharge", Descriptors.MinPartialCharge),
        ("MaxAbsPartialCharge", Descriptors.MaxAbsPartialCharge),
        ("MinAbsPartialCharge", Descriptors.MinAbsPartialCharge),
        ("BalabanJ", GraphDescriptors.BalabanJ),
        ("BertzCT", GraphDescriptors.BertzCT),
        ("HallKierAlpha", Descriptors.HallKierAlpha),
        ("Kappa1", Descriptors.Kappa1),
        ("Kappa2", Descriptors.Kappa2),
        ("Kappa3", Descriptors.Kappa3),
        ("Chi0n", Descriptors.Chi0n),
        ("Chi1n", Descriptors.Chi1n),
        ("Chi2n", Descriptors.Chi2n),
        ("Chi3n", Descriptors.Chi3n),
        ("Chi4n", Descriptors.Chi4n),
        ("Chi0v", Descriptors.Chi0v),
        ("Chi1v", Descriptors.Chi1v),
        ("Chi2v", Descriptors.Chi2v),
        ("Chi3v", Descriptors.Chi3v),
        ("Chi4v", Descriptors.Chi4v),
        ("Ipc", Descriptors.Ipc),
    ]

    # 3D 描述符（需要构象）
    _3D_DESCRIPTORS: List[Tuple[str, Callable]] = [
        ("Asphericity", Descriptors3D.Asphericity),
        ("Eccentricity", Descriptors3D.Eccentricity),
        ("InertialShapeFactor", Descriptors3D.InertialShapeFactor),
        ("NPR1", Descriptors3D.NPR1),
        ("NPR2", Descriptors3D.NPR2),
        ("PMI1", Descriptors3D.PMI1),
        ("PMI2", Descriptors3D.PMI2),
        ("PMI3", Descriptors3D.PMI3),
        ("RadiusOfGyration", Descriptors3D.RadiusOfGyration),
        ("SpherocityIndex", Descriptors3D.SpherocityIndex),
    ]

    def __init__(
        self,
        descriptor_set: Union[str, DescriptorSet] = DescriptorSet.BASIC,
        custom_descriptors: Optional[Dict[str, Callable[[Chem.Mol], Any]]] = None,
        include_3d: bool = False,
    ) -> None:
        """初始化描述符计算器.

        Args:
            descriptor_set: 预定义描述符集合名称或枚举.
            custom_descriptors: 自定义描述符函数字典（名称 -> 函数）.
            include_3d: 是否包含 3D 描述符（需先优化构象）.
        """
        self.descriptor_set_name = (
            descriptor_set if isinstance(descriptor_set, str) else descriptor_set.value
        )
        self.custom_descriptors = custom_descriptors or {}
        self.include_3d = include_3d
        self._descriptors = self._build_descriptor_list()

    def _build_descriptor_list(self) -> List[Tuple[str, Callable]]:
        """根据配置构建描述符列表."""
        descs: List[Tuple[str, Callable]] = []

        if self.descriptor_set_name == "all_2d":
            descs.extend(self._ALL_2D_DESCRIPTORS)
        elif self.descriptor_set_name in self._DESCRIPTOR_REGISTRY:
            descs.extend(self._DESCRIPTOR_REGISTRY[self.descriptor_set_name])
        elif self.descriptor_set_name == "custom":
            pass  # 仅使用自定义描述符
        else:
            logger.warning(
                f"Unknown descriptor set '{self.descriptor_set_name}', "
                "falling back to 'basic'"
            )
            descs.extend(self._DESCRIPTOR_REGISTRY["basic"])

        # 添加自定义描述符
        for name, func in self.custom_descriptors.items():
            descs.append((name, func))

        # 可选添加 3D 描述符
        if self.include_3d:
            descs.extend(self._3D_DESCRIPTORS)

        return descs

    def compute(self, mol: Chem.Mol) -> DescriptorResult:
        """计算单个分子的描述符.

        Args:
            mol: RDKit 分子对象.

        Returns:
            描述符计算结果.
        """
        if mol is None:
            return DescriptorResult(success=False, errors=["Input mol is None"])

        result = DescriptorResult(mol=mol)
        for name, func in self._descriptors:
            try:
                value = func(mol)
                # 将 RDKit 的显式类型转换为 Python 原生类型
                if hasattr(value, "__float__"):
                    value = float(value)
                elif hasattr(value, "__int__"):
                    value = int(value)
                result.values[name] = value
            except Exception as e:
                result.errors.append(f"{name}: {e}")
                logger.debug(f"Descriptor '{name}' failed: {e}")

        return result

    def compute_batch(
        self,
        molecules: List[Chem.Mol],
        names: Optional[List[str]] = None,
    ) -> List[DescriptorResult]:
        """批量计算分子描述符.

        Args:
            molecules: RDKit 分子对象列表.
            names: 可选的分子名称列表（用于日志）.

        Returns:
            描述符结果列表.
        """
        results = []
        for i, mol in enumerate(molecules):
            result = self.compute(mol)
            results.append(result)
            if result.errors and names:
                logger.warning(
                    f"Descriptor errors for {names[i]}: {result.errors}"
                )
        return results

    def compute_molecule_entry(self, entry) -> DescriptorResult:
        """对 MoleculeEntry 计算描述符（便捷方法）.

        Args:
            entry: MoleculeEntry 对象（需有 mol 属性）.

        Returns:
            描述符计算结果.
        """
        return self.compute(entry.mol)

    def available_descriptors(self) -> List[str]:
        """获取当前配置下所有可用的描述符名称.

        Returns:
            描述符名称列表.
        """
        return [name for name, _ in self._descriptors]

    def add_descriptor(self, name: str, func: Callable[[Chem.Mol], Any]) -> None:
        """动态添加自定义描述符.

        Args:
            name: 描述符名称.
            func: 描述符计算函数.
        """
        self._descriptors.append((name, func))
        self.custom_descriptors[name] = func

    def remove_descriptor(self, name: str) -> bool:
        """移除指定描述符.

        Args:
            name: 要移除的描述符名称.

        Returns:
            成功移除返回 True，未找到返回 False.
        """
        original_len = len(self._descriptors)
        self._descriptors = [(n, f) for n, f in self._descriptors if n != name]
        return len(self._descriptors) < original_len

    @staticmethod
    def list_builtin_sets() -> List[str]:
        """列出所有内置描述符集合名称.

        Returns:
            描述符集合名称列表.
        """
        return list(MoleculeDescriptorCalculator._DESCRIPTOR_REGISTRY.keys()) + [
            "all_2d",
            "custom",
        ]
