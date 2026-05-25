"""分子过滤器模块.

提供多种常用的分子过滤规则，包括 Lipinski 五规则、Veber 规则、PAINS 过滤器、
毒性子结构过滤等。支持过滤器组合和自定义过滤逻辑。

核心类:
    MoleculeFilter: 过滤器基类
    LipinskiFilter: Lipinski 五规则（类药性）
    VeberFilter: Veber 规则（口服生物利用度）
    PAINSFilter: PAINS 过滤器（泛分析干扰化合物）
    CompositeFilter: 组合过滤器

示例:
    >>> filter = CompositeFilter([LipinskiFilter(), VeberFilter()])
    >>> if filter.accept(mol):
    ...     print("Passed drug-likeness filters")
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """过滤结果.

    属性:
        passed: 是否通过过滤.
        reasons: 未通过的原因列表（通过时为空）.
        details: 详细的键值对结果（如各规则的具体值）.
    """

    passed: bool = True
    reasons: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        """支持直接判断：if result:."""
        return self.passed


class MoleculeFilter(ABC):
    """分子过滤器抽象基类.

    所有具体过滤器的基类，定义统一接口。
    """

    @abstractmethod
    def filter(self, mol: Chem.Mol) -> FilterResult:
        """对单个分子进行过滤判断.

        Args:
            mol: RDKit 分子对象.

        Returns:
            过滤结果.
        """
        pass

    def accept(self, mol: Chem.Mol) -> bool:
        """便捷方法：直接返回是否通过.

        Args:
            mol: RDKit 分子对象.

        Returns:
            通过返回 True，否则 False.
        """
        return self.filter(mol).passed

    def filter_batch(
        self, molecules: list[Chem.Mol], names: list[str] | None = None
    ) -> list[FilterResult]:
        """批量过滤.

        Args:
            molecules: 分子列表.
            names: 可选的分子名称列表.

        Returns:
            过滤结果列表.
        """
        results = []
        for i, mol in enumerate(molecules):
            result = self.filter(mol)
            results.append(result)
            if not result.passed and names:
                logger.debug(f"Filter rejected {names[i]}: {result.reasons}")
        return results


class LipinskiFilter(MoleculeFilter):
    """Lipinski 五规则过滤器（类药性规则）.

    规则:
        1. 分子量 ≤ 500 Da
        2. LogP ≤ 5
        3. 氢键供体数（HBD） ≤ 5
        4. 氢键受体数（HBA） ≤ 10
        5. （可选）可旋转键数 ≤ 10

    默认允许最多违反 1 条规则（即通过 4/5 即可）。

    属性:
        max_violations: 最大允许违反的规则数.
        include_rotatable_bonds: 是否将可旋转键数作为第 5 条规则.
    """

    def __init__(
        self,
        max_violations: int = 1,
        include_rotatable_bonds: bool = False,
    ) -> None:
        """初始化 Lipinski 过滤器.

        Args:
            max_violations: 最大允许违反的规则数，默认为 1.
            include_rotatable_bonds: 是否包含可旋转键规则，默认为 False.
        """
        self.max_violations = max_violations
        self.include_rotatable_bonds = include_rotatable_bonds

    def filter(self, mol: Chem.Mol) -> FilterResult:
        """执行 Lipinski 规则过滤."""
        if mol is None:
            return FilterResult(passed=False, reasons=["mol is None"])

        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        hba = rdMolDescriptors.CalcNumHBA(mol)
        rot = rdMolDescriptors.CalcNumRotatableBonds(mol)

        violations = 0
        reasons = []

        if mw > 500:
            violations += 1
            reasons.append(f"MW = {mw:.1f} > 500")
        if logp > 5:
            violations += 1
            reasons.append(f"LogP = {logp:.2f} > 5")
        if hbd > 5:
            violations += 1
            reasons.append(f"HBD = {hbd} > 5")
        if hba > 10:
            violations += 1
            reasons.append(f"HBA = {hba} > 10")
        if self.include_rotatable_bonds and rot > 10:
            violations += 1
            reasons.append(f"Rotatable bonds = {rot} > 10")

        passed = violations <= self.max_violations
        return FilterResult(
            passed=passed,
            reasons=reasons,
            details={
                "MW": mw,
                "LogP": logp,
                "HBD": hbd,
                "HBA": hba,
                "RotatableBonds": rot,
                "Violations": violations,
            },
        )

    def __repr__(self) -> str:
        return (
            f"LipinskiFilter(max_violations={self.max_violations}, "
            f"include_rotatable_bonds={self.include_rotatable_bonds})"
        )


class VeberFilter(MoleculeFilter):
    """Veber 规则过滤器（口服生物利用度）.

    规则:
        1. 可旋转键数 ≤ 10
        2. TPSA ≤ 140 Å²（或 HBD + HBA ≤ 12）

    属性:
        max_rotatable_bonds: 最大可旋转键数.
        max_tpsa: 最大 TPSA.
        use_hb_count: 是否使用 HBD + HBA ≤ 12 替代 TPSA.
    """

    def __init__(
        self,
        max_rotatable_bonds: int = 10,
        max_tpsa: float = 140.0,
        use_hb_count: bool = False,
    ) -> None:
        """初始化 Veber 过滤器.

        Args:
            max_rotatable_bonds: 最大可旋转键数，默认为 10.
            max_tpsa: 最大 TPSA，默认为 140.0.
            use_hb_count: 使用 HBD+HBA 替代 TPSA，默认为 False.
        """
        self.max_rotatable_bonds = max_rotatable_bonds
        self.max_tpsa = max_tpsa
        self.use_hb_count = use_hb_count

    def filter(self, mol: Chem.Mol) -> FilterResult:
        """执行 Veber 规则过滤."""
        if mol is None:
            return FilterResult(passed=False, reasons=["mol is None"])

        rot = rdMolDescriptors.CalcNumRotatableBonds(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        hba = rdMolDescriptors.CalcNumHBA(mol)
        hb_count = hbd + hba

        reasons = []

        if rot > self.max_rotatable_bonds:
            reasons.append(f"Rotatable bonds = {rot} > {self.max_rotatable_bonds}")

        if self.use_hb_count:
            if hb_count > 12:
                reasons.append(f"HBD + HBA = {hb_count} > 12")
        else:
            if tpsa > self.max_tpsa:
                reasons.append(f"TPSA = {tpsa:.1f} > {self.max_tpsa}")

        return FilterResult(
            passed=len(reasons) == 0,
            reasons=reasons,
            details={
                "RotatableBonds": rot,
                "TPSA": tpsa,
                "HBD": hbd,
                "HBA": hba,
                "HBCount": hb_count,
            },
        )


class PAINSFilter(MoleculeFilter):
    """PAINS 过滤器（泛分析干扰化合物）.

    使用 RDKit 的 FilterCatalog 检测 PAINS 子结构。
    PAINS（Pan-Assay Interference Compounds）是在多种生物分析中
    频繁出现假阳性信号的化合物类别。

    属性:
        catalog: RDKit FilterCatalog 对象.
    """

    def __init__(self) -> None:
        """初始化 PAINS 过滤器."""
        params = FilterCatalogParams()
        params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
        self.catalog = FilterCatalog(params)

    def filter(self, mol: Chem.Mol) -> FilterResult:
        """执行 PAINS 过滤.

        注意：PAINS 过滤器的语义是"匹配到 PAINS 则**不通过**"，
        即包含 PAINS 子结构的化合物被认为是不良的。
        """
        if mol is None:
            return FilterResult(passed=False, reasons=["mol is None"])

        entry = self.catalog.GetFirstMatch(mol)
        if entry is not None:
            return FilterResult(
                passed=False,
                reasons=[f"PAINS match: {entry.GetDescription()}"],
                details={"PAINS": entry.GetDescription()},
            )
        return FilterResult(passed=True, details={"PAINS": None})

    def filter_all_matches(self, mol: Chem.Mol) -> FilterResult:
        """获取所有 PAINS 匹配（不仅是第一个）.

        Args:
            mol: RDKit 分子对象.

        Returns:
            包含所有匹配项的过滤结果.
        """
        if mol is None:
            return FilterResult(passed=False, reasons=["mol is None"])

        matches = self.catalog.GetMatches(mol)
        if matches:
            reasons = [m.GetDescription() for m in matches]
            return FilterResult(
                passed=False,
                reasons=reasons,
                details={"PAINS_matches": reasons},
            )
        return FilterResult(passed=True, details={"PAINS_matches": []})


class ToxicityFilter(MoleculeFilter):
    """毒性子结构过滤器.

    检测已知毒性相关的化学子结构（如 Michael 受体、环氧乙烷等）。
    使用 RDKit 的 FilterCatalog 的 BRENK 目录。

    属性:
        catalog: RDKit FilterCatalog 对象.
    """

    def __init__(self) -> None:
        """初始化毒性过滤器."""
        params = FilterCatalogParams()
        params.AddCatalog(FilterCatalogParams.FilterCatalogs.BRENK)
        self.catalog = FilterCatalog(params)

    def filter(self, mol: Chem.Mol) -> FilterResult:
        """执行毒性子结构过滤."""
        if mol is None:
            return FilterResult(passed=False, reasons=["mol is None"])

        entry = self.catalog.GetFirstMatch(mol)
        if entry is not None:
            return FilterResult(
                passed=False,
                reasons=[f"Toxicity alert: {entry.GetDescription()}"],
                details={"Toxicity": entry.GetDescription()},
            )
        return FilterResult(passed=True, details={"Toxicity": None})


class MolecularWeightFilter(MoleculeFilter):
    """分子量范围过滤器.

    属性:
        min_mw: 最小分子量（含）.
        max_mw: 最大分子量（含）.
    """

    def __init__(
        self,
        min_mw: float = 0.0,
        max_mw: float = float("inf"),
    ) -> None:
        """初始化分子量过滤器.

        Args:
            min_mw: 最小分子量，默认为 0.0.
            max_mw: 最大分子量，默认为正无穷.
        """
        self.min_mw = min_mw
        self.max_mw = max_mw

    def filter(self, mol: Chem.Mol) -> FilterResult:
        """执行分子量过滤."""
        if mol is None:
            return FilterResult(passed=False, reasons=["mol is None"])

        mw = Descriptors.MolWt(mol)
        reasons = []

        if mw < self.min_mw:
            reasons.append(f"MW = {mw:.1f} < {self.min_mw}")
        if mw > self.max_mw:
            reasons.append(f"MW = {mw:.1f} > {self.max_mw}")

        return FilterResult(
            passed=len(reasons) == 0,
            reasons=reasons,
            details={"MW": mw},
        )


class RingCountFilter(MoleculeFilter):
    """环数过滤器.

    属性:
        min_rings: 最小环数.
        max_rings: 最大环数.
    """

    def __init__(
        self,
        min_rings: int = 0,
        max_rings: int = 10,
    ) -> None:
        """初始化环数过滤器.

        Args:
            min_rings: 最小环数，默认为 0.
            max_rings: 最大环数，默认为 10.
        """
        self.min_rings = min_rings
        self.max_rings = max_rings

    def filter(self, mol: Chem.Mol) -> FilterResult:
        """执行环数过滤."""
        if mol is None:
            return FilterResult(passed=False, reasons=["mol is None"])

        num_rings = rdMolDescriptors.CalcNumRings(mol)
        reasons = []

        if num_rings < self.min_rings:
            reasons.append(f"Rings = {num_rings} < {self.min_rings}")
        if num_rings > self.max_rings:
            reasons.append(f"Rings = {num_rings} > {self.max_rings}")

        return FilterResult(
            passed=len(reasons) == 0,
            reasons=reasons,
            details={"NumRings": num_rings},
        )


class CustomFilter(MoleculeFilter):
    """自定义过滤器.

    允许通过传入谓词函数和描述来快速创建过滤器。

    属性:
        predicate: 接受 mol 返回 bool 的函数.
        description: 过滤器描述.
    """

    def __init__(
        self,
        predicate,
        description: str = "custom",
    ) -> None:
        """初始化自定义过滤器.

        Args:
            predicate: 过滤谓词函数.
            description: 过滤器描述.
        """
        self.predicate = predicate
        self.description = description

    def filter(self, mol: Chem.Mol) -> FilterResult:
        """执行自定义过滤."""
        if mol is None:
            return FilterResult(passed=False, reasons=["mol is None"])

        if self.predicate(mol):
            return FilterResult(passed=True)
        return FilterResult(
            passed=False,
            reasons=[f"Failed custom filter: {self.description}"],
        )


class CompositeFilter(MoleculeFilter):
    """组合过滤器.

    将多个过滤器组合在一起，支持 AND（默认）和 OR 两种逻辑模式。

    属性:
        filters: 子过滤器列表.
        mode: 组合模式，"and" 或 "or".
    """

    def __init__(
        self,
        filters: list[MoleculeFilter],
        mode: str = "and",
    ) -> None:
        """初始化组合过滤器.

        Args:
            filters: 子过滤器列表.
            mode: 组合模式，"and" 要求全部通过，"or" 要求至少一个通过.
        """
        if mode not in ("and", "or"):
            raise ValueError("mode must be 'and' or 'or'")
        self.filters = filters
        self.mode = mode

    def filter(self, mol: Chem.Mol) -> FilterResult:
        """执行组合过滤."""
        if mol is None:
            return FilterResult(passed=False, reasons=["mol is None"])

        all_reasons = []
        all_details: dict[str, Any] = {}
        passed_count = 0

        for f in self.filters:
            result = f.filter(mol)
            all_details.update(result.details)
            if result.passed:
                passed_count += 1
            else:
                all_reasons.extend(result.reasons)

        if self.mode == "and":
            passed = passed_count == len(self.filters)
        else:  # "or"
            passed = passed_count > 0
            if passed:
                all_reasons = []  # OR 模式下通过时不需要原因

        return FilterResult(
            passed=passed,
            reasons=all_reasons,
            details=all_details,
        )

    def __repr__(self) -> str:
        return f"CompositeFilter(filters={len(self.filters)}, mode='{self.mode}')"


# 便捷工厂函数


def drug_likeness_filter(
    max_lipinski_violations: int = 1,
    include_veber: bool = True,
    include_pains: bool = True,
) -> CompositeFilter:
    """创建标准类药性组合过滤器.

    Args:
        max_lipinski_violations: Lipinski 最大允许违反数.
        include_veber: 是否包含 Veber 规则.
        include_pains: 是否包含 PAINS 过滤.

    Returns:
        组合过滤器.
    """
    filters: list[MoleculeFilter] = [
        LipinskiFilter(max_violations=max_lipinski_violations),
    ]
    if include_veber:
        filters.append(VeberFilter())
    if include_pains:
        filters.append(PAINSFilter())
    return CompositeFilter(filters, mode="and")


def lead_likeness_filter() -> CompositeFilter:
    """创建先导化合物过滤器（更严格的标准）.

    标准:
        - 分子量 250-350
        - LogP 1-3
        - 环数 1-3
        - HBD ≤ 3, HBA ≤ 6
        - 可旋转键 ≤ 7

    Returns:
        组合过滤器.
    """
    filters: list[MoleculeFilter] = [
        MolecularWeightFilter(min_mw=250, max_mw=350),
        RingCountFilter(min_rings=1, max_rings=3),
        LipinskiFilter(max_violations=0, include_rotatable_bonds=True),
        CustomFilter(
            lambda m: 1 <= Descriptors.MolLogP(m) <= 3,
            description="LogP 1-3",
        ),
    ]
    return CompositeFilter(filters, mode="and")
