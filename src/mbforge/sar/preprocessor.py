"""活性数据预处理器模块.

本模块提供活性数据的自动清洗和标准化功能。
在药物化学中，原始活性数据通常存在以下问题需要处理:
  - 单位不统一 (nM / μM / mM 混用)
  - 删失数据 (">10000", "<50" 等符号表示)
  - 异常值 (实验误差或假阳性)
  - 需要转换为 pActivity 尺度进行统计

主要组件:
  - ActivityPreprocessor: 活性数据预处理器
  - DataQualityReport: 数据质量报告
  - ActivityUnit: 活性单位枚举

示例:
    >>> from mbforge.sar.preprocessor import ActivityPreprocessor
    >>> preprocessor = ActivityPreprocessor()
    >>> molecules = preprocessor.process(molecules, unit_column="IC50_unit")
    >>> report = preprocessor.get_quality_report()
    >>> print(report.summary())
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..mcs.finder import MCSResult

logger = logging.getLogger(__name__)


class ActivityUnit(Enum):
    """活性单位枚举."""
    NM = "nM"
    UM = "uM"
    MM = "mM"
    UNKNOWN = "unknown"


# 单位转换因子: 转换为 nM
UNIT_TO_NM: Dict[ActivityUnit, float] = {
    ActivityUnit.NM: 1.0,
    ActivityUnit.UM: 1000.0,
    ActivityUnit.MM: 1_000_000.0,
    ActivityUnit.UNKNOWN: 1.0,
}


class CensoredType(Enum):
    """删失数据类型."""
    NONE = "none"
    GREATER_THAN = ">"  # 右删失: 活性 > X (实际可能更高)
    LESS_THAN = "<"  # 左删失: 活性 < X (实际可能更低)
    TILDE = "~"  # 近似值: ~X


@dataclass
class CensoredValue:
    """删失活性值.

    Attributes:
        value: 删失界限值.
        censored_type: 删失类型.
        raw_string: 原始字符串.
    """
    value: float
    censored_type: CensoredType
    raw_string: str


@dataclass
class ProcessedActivity:
    """处理后的活性信息.

    Attributes:
        raw: 原始字符串/数值.
        value_nm: 标准化为 nM 后的数值.
        p_value: pActivity 值 (-log10(Activity_M)).
        censored: 删失信息.
        is_outlier: 是否是异常值.
        unit: 检测到的单位.
    """
    raw: str
    value_nm: Optional[float] = None
    p_value: Optional[float] = None
    censored: Optional[CensoredValue] = None
    is_outlier: bool = False
    unit: ActivityUnit = ActivityUnit.UNKNOWN


@dataclass
class DataQualityReport:
    """数据质量报告.

    Attributes:
        total_molecules: 总分子数.
        valid_activities: 有效活性值数.
        invalid_activities: 无效活性值数.
        censored_values: 删失值数.
        outliers: 检测到的异常值数.
        unit_counts: 各单位的计数.
        activity_range: 活性值范围 (min, max).
        p_activity_range: pActivity 范围.
    """
    total_molecules: int = 0
    valid_activities: int = 0
    invalid_activities: int = 0
    censored_values: int = 0
    outliers: int = 0
    unit_counts: Dict[str, int] = field(default_factory=dict)
    activity_range: Tuple[Optional[float], Optional[float]] = (None, None)
    p_activity_range: Tuple[Optional[float], Optional[float]] = (None, None)
    failed_molecules: List[Dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        """生成可读的摘要报告."""
        lines = [
            "=" * 50,
            "数据质量报告",
            "=" * 50,
            f"总分子数: {self.total_molecules}",
            f"有效活性值: {self.valid_activities}",
            f"无效活性值: {self.invalid_activities}",
            f"删失值数: {self.censored_values}",
            f"异常值数: {self.outliers}",
            f"失败分子数: {len(self.failed_molecules)}",
            "",
            "单位分布:",
        ]
        for unit, count in sorted(self.unit_counts.items()):
            lines.append(f"  {unit}: {count}")

        if self.valid_activities > 0:
            min_act, max_act = self.activity_range
            lines.extend([
                "",
                f"活性范围 (nM): {min_act:.2f} - {max_act:.2f}",
            ])
            if self.p_activity_range[0] is not None:
                min_p, max_p = self.p_activity_range
                lines.append(f"pActivity 范围: {min_p:.2f} - {max_p:.2f}")

        lines.append("=" * 50)
        return "\n".join(lines)


class ActivityPreprocessor:
    """活性数据预处理器.

    自动检测并标准化活性数据，支持:
      - 单位自动识别与转换 (nM / μM / mM → nM)
      - 删失数据处理 (>, <, ~)
      - pActivity 转换 (pIC50 = -log10(IC50_M))
      - IQR 异常值检测
      - 数据质量报告生成

    Attributes:
        iqr_multiplier: IQR 异常值检测的倍数，默认 1.5.
        enable_p_conversion: 是否启用 pActivity 转换，默认 True.
        enable_outlier_detection: 是否启用异常值检测，默认 True.
        censor_treatment: 删失数据处理方式 ("ignore" / "as_is" / "conservative").

    示例:
        >>> processor = ActivityPreprocessor(iqr_multiplier=2.0)
        >>> molecules = processor.process(molecules)
        >>> report = processor.get_quality_report()
        >>> for m in molecules:
        ...     print(f"{m['name']}: pIC50 = {m.get('p_activity'):.2f}")
    """

    # 单位检测正则表达式模式
    _UNIT_PATTERNS = {
        ActivityUnit.NM: re.compile(r"(?i)(nm|nanomolar|n ?molar)"),
        ActivityUnit.UM: re.compile(r"(?i)(u[mμ]|[\u00b5]m|micromolar|micro ?molar)"),
        ActivityUnit.MM: re.compile(r"(?i)(mm|millimolar|milli ?molar)"),
    }

    # 删失数据模式
    _CENSORED_PATTERNS = [
        (re.compile(r"^\s*>\s*([\d.]+)\s*$"), CensoredType.GREATER_THAN),
        (re.compile(r"^\s*<\s*([\d.]+)\s*$"), CensoredType.LESS_THAN),
        (re.compile(r"^\s*~\s*([\d.]+)\s*$"), CensoredType.TILDE),
        (re.compile(r"^\s*approx\.?\s*([\d.]+)\s*$"), CensoredType.TILDE),
    ]

    def __init__(
        self,
        iqr_multiplier: float = 1.5,
        enable_p_conversion: bool = True,
        enable_outlier_detection: bool = True,
        censor_treatment: str = "conservative",
    ) -> None:
        """初始化活性数据预处理器.

        Args:
            iqr_multiplier: IQR 倍数，默认 1.5 (Tukey's fences).
                增大此值会减少标记为异常值的数量.
            enable_p_conversion: 是否计算 pActivity，默认 True.
            enable_outlier_detection: 是否检测异常值，默认 True.
            censor_treatment: 删失数据处理方式:
                - "conservative": 删失数据标记但不用于统计 (默认)
                - "as_is": 删失数据当作普通数值处理
                - "ignore": 忽略删失标记
        """
        self.iqr_multiplier = iqr_multiplier
        self.enable_p_conversion = enable_p_conversion
        self.enable_outlier_detection = enable_outlier_detection
        self.censor_treatment = censor_treatment
        self._report = DataQualityReport()

    def detect_unit(self, raw_value: str) -> ActivityUnit:
        """检测活性值的单位.

        通过正则表达式匹配原始值字符串中的单位关键词。

        Args:
            raw_value: 原始活性值字符串.

        Returns:
            ActivityUnit 枚举值.
        """
        for unit, pattern in self._UNIT_PATTERNS.items():
            if pattern.search(raw_value):
                return unit
        return ActivityUnit.UNKNOWN

    def parse_censored(self, raw_value: str) -> Optional[CensoredValue]:
        """解析删失数据标记.

        Args:
            raw_value: 原始活性值字符串.

        Returns:
            CensoredValue 对象，如果不是删失数据则返回 None.
        """
        for pattern, ctype in self._CENSORED_PATTERNS:
            match = pattern.match(raw_value)
            if match:
                try:
                    value = float(match.group(1))
                    return CensoredValue(value=value, censored_type=ctype, raw_string=raw_value)
                except ValueError:
                    continue
        return None

    def clean_numeric(self, raw_value: str) -> Tuple[Optional[float], ActivityUnit, Optional[CensoredValue]]:
        """清洗并解析原始活性值.

        从混合了单位、符号和数值的字符串中提取数值。
        支持格式如:
          - "12.5 nM"
          - "<100"
          - ">10000"
          - "~50"
          - "0.5 uM"
          - "0.001 mM"

        Args:
            raw_value: 原始活性值字符串.

        Returns:
            (数值, 单位, 删失信息) 三元组.
            数值为 None 表示解析失败.
        """
        if not raw_value or not isinstance(raw_value, str):
            return None, ActivityUnit.UNKNOWN, None

        raw_stripped = raw_value.strip()

        # 先检查是否为删失数据
        censored = self.parse_censored(raw_stripped)
        if censored:
            # 尝试从字符串中提取单位信息
            remainder = raw_stripped
            for pattern, _ in self._CENSORED_PATTERNS:
                remainder = pattern.sub("", raw_stripped).strip()
            unit = self.detect_unit(remainder) if remainder else ActivityUnit.UNKNOWN
            return censored.value, unit, censored

        # 尝试提取数值和单位
        numeric_pattern = re.compile(
            r"^\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([a-zA-Z\u00b5uμ]*\s*[mM]?[a-zA-Z]*)?\s*$"
        )
        match = numeric_pattern.match(raw_stripped)
        if match:
            try:
                value = float(match.group(1))
                unit_str = match.group(2) or ""
                unit = self.detect_unit(unit_str)
                return value, unit, None
            except ValueError:
                return None, ActivityUnit.UNKNOWN, None

        # 纯数字
        try:
            return float(raw_stripped), ActivityUnit.NM, None
        except ValueError:
            return None, ActivityUnit.UNKNOWN, None

    def convert_to_nm(self, value: float, unit: ActivityUnit) -> float:
        """将活性值转换为 nM.

        Args:
            value: 活性数值.
            unit: 单位.

        Returns:
            转换为 nM 后的值.
        """
        return value * UNIT_TO_NM.get(unit, 1.0)

    def to_p_activity(self, value_nm: float) -> float:
        """将 nM 活性值转换为 pActivity.

        pIC50 = -log10(IC50_M) = -log10(IC50_nM * 1e-9) = 9 - log10(IC50_nM)

        Args:
            value_nm: nM 单位的 IC50 值.

        Returns:
            pActivity 值 (pIC50 / pEC50).
        """
        if value_nm <= 0:
            return 0.0
        return 9.0 - np.log10(value_nm)

    def detect_outliers_iqr(self, values: List[float]) -> List[bool]:
        """使用 IQR 方法检测异常值.

        使用 Tukey's fences 方法: Q1 - 1.5*IQR 和 Q3 + 1.5*IQR 之外的值被视为异常值.

        Args:
            values: 活性值列表 (nM).

        Returns:
            bool 列表，True 表示该值是异常值.
        """
        if len(values) < 4:
            return [False] * len(values)

        arr = np.array(values)
        q1 = np.percentile(arr, 25)
        q3 = np.percentile(arr, 75)
        iqr = q3 - q1

        lower_bound = q1 - self.iqr_multiplier * iqr
        upper_bound = q3 + self.iqr_multiplier * iqr

        return [(v < lower_bound or v > upper_bound) for v in values]

    def process_molecule(
        self, mol_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """处理单个分子的活性数据.

        Args:
            mol_data: 分子字典，需包含 'activity_raw' 或 'activity' 键.

        Returns:
            添加了处理字段的分子字典:
                - 'activity': 标准化后的 nM 值
                - 'activity_raw': 原始值 (不变)
                - 'p_activity': pActivity 值 (可选)
                - 'activity_censored': 删失信息 (可选)
                - 'activity_unit': 检测到的单位
                - 'is_outlier': 是否是异常值
            处理失败时返回 None (不删除分子，保留原始数据).
        """
        result = dict(mol_data)

        raw = mol_data.get("activity_raw", "")
        current_activity = mol_data.get("activity")

        # 如果已有 numeric activity，尝试单位检测
        if current_activity is not None and raw:
            # 原始值中有单位信息
            parsed_value, unit, censored = self.clean_numeric(str(raw))
            if parsed_value is not None:
                # 将原始解析值转换为 nM
                result["activity_nm_raw"] = self.convert_to_nm(parsed_value, unit)
                # 如果已有 activity 的单位不同，也用 nM 标准化
                if unit != ActivityUnit.NM and unit != ActivityUnit.UNKNOWN:
                    result["activity"] = self.convert_to_nm(current_activity, unit)
                else:
                    result["activity"] = current_activity
            else:
                result["activity"] = current_activity
            result["activity_unit"] = unit
            result["activity_censored"] = censored
        elif current_activity is not None:
            # 纯数值，默认为 nM
            result["activity_unit"] = ActivityUnit.NM
            result["activity_censored"] = None
        elif raw:
            # 尝试从原始字符串解析
            parsed_value, unit, censored = self.clean_numeric(str(raw))
            if parsed_value is not None:
                value_nm = self.convert_to_nm(parsed_value, unit)
                result["activity"] = value_nm
                result["activity_unit"] = unit
                result["activity_censored"] = censored
            else:
                result["activity_unit"] = ActivityUnit.UNKNOWN
                result["activity_censored"] = None

        return result

    def process(
        self,
        molecules: List[Dict[str, Any]],
        activity_key: str = "activity",
        raw_key: str = "activity_raw",
    ) -> List[Dict[str, Any]]:
        """批量处理分子的活性数据.

        执行完整的预处理流程:
          1. 解析原始活性值 (单位检测、删失识别)
          2. 标准化为 nM
          3. 计算 pActivity (可选)
          4. 异常值检测 (可选)
          5. 生成数据质量报告

        Args:
            molecules: 分子字典列表.
            activity_key: 活性值的键名，默认 "activity".
            raw_key: 原始活性字符串的键名，默认 "activity_raw".

        Returns:
            处理后的分子字典列表 (不改变原始列表).
        """
        self._report = DataQualityReport()
        self._report.total_molecules = len(molecules)

        processed_molecules: List[Dict[str, Any]] = []
        all_nm_values: List[float] = []

        for mol in molecules:
            try:
                processed = self.process_molecule(mol)
                if processed is not None:
                    processed_molecules.append(processed)
                    activity_val = processed.get(activity_key)
                    if activity_val is not None:
                        censored = processed.get("activity_censored")
                        if censored and self.censor_treatment == "conservative":
                            self._report.censored_values += 1
                        else:
                            all_nm_values.append(float(activity_val))
                            self._report.valid_activities += 1

                        unit = processed.get("activity_unit", ActivityUnit.UNKNOWN)
                        unit_name = unit.value
                        self._report.unit_counts[unit_name] = \
                            self._report.unit_counts.get(unit_name, 0) + 1
                else:
                    processed_molecules.append(mol)
                    self._report.invalid_activities += 1
                    self._report.failed_molecules.append(mol)
            except Exception as e:
                logger.warning(f"Failed to process molecule {mol.get('name', 'unknown')}: {e}")
                processed_molecules.append(mol)
                self._report.failed_molecules.append(mol)

        # 异常值检测
        if self.enable_outlier_detection and all_nm_values:
            outliers = self.detect_outliers_iqr(all_nm_values)
            outlier_idx = 0
            for mol in processed_molecules:
                val = mol.get(activity_key)
                if val is not None:
                    censored = mol.get("activity_censored")
                    if censored and self.censor_treatment == "conservative":
                        mol["is_outlier"] = False
                    else:
                        mol["is_outlier"] = outliers[outlier_idx]
                        if outliers[outlier_idx]:
                            self._report.outliers += 1
                        outlier_idx += 1
                else:
                    mol["is_outlier"] = False

        # pActivity 转换
        if self.enable_p_conversion:
            for mol in processed_molecules:
                val_nm = mol.get(activity_key)
                if val_nm is not None:
                    mol["p_activity"] = self.to_p_activity(float(val_nm))

        # 更新报告
        if all_nm_values:
            self._report.activity_range = (float(np.min(all_nm_values)), float(np.max(all_nm_values)))
            p_values = [self.to_p_activity(v) for v in all_nm_values]
            self._report.p_activity_range = (float(np.min(p_values)), float(np.max(p_values)))

        logger.info(f"Activity preprocessing complete: {len(processed_molecules)} molecules processed")
        logger.info(f"  Valid activities: {self._report.valid_activities}")
        logger.info(f"  Censored values: {self._report.censored_values}")
        logger.info(f"  Outliers detected: {self._report.outliers}")
        if self._report.failed_molecules:
            logger.warning(f"  Failed molecules: {len(self._report.failed_molecules)}")

        return processed_molecules

    def get_quality_report(self) -> DataQualityReport:
        """获取数据质量报告.

        Returns:
            当前处理会话的数据质量报告.
        """
        return self._report
