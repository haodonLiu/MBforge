"""关联引擎 — 将图像检测到的分子与附近文本关联.

负责从 ROI 提取的文本上下文中解析：
- 化合物名称 / Figure 编号
- 生物活性数据（IC50, EC50, Ki, Kd, EC90 等）
- 其他元数据（细胞系、实验条件等）

输出回填到 ExtractionResult.name / context_text / properties。
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from mbforge.parsers.extraction_result import ExtractionResult
from mbforge.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 正则模式
# ---------------------------------------------------------------------------

# 化合物编号：Compound 1, Fig. 1A, Scheme 2 等
_COMPOUND_NAME_PATTERNS = [
    re.compile(r"Compound\s+(\d+[a-zA-Z]?)", re.IGNORECASE),
    re.compile(r"Fig(?:ure)?\.?\s*(\d+[a-zA-Z]?)", re.IGNORECASE),
    re.compile(r"Scheme\s+(\d+[a-zA-Z]?)", re.IGNORECASE),
    re.compile(r"Table\s+(\d+[a-zA-Z]?)", re.IGNORECASE),
]

# 活性数据：IC50 = 5.2 nM, EC50: 0.1 µM, Ki of 3.4 nM
_ACTIVITY_PATTERNS = [
    # IC50 = 5.2 nM
    re.compile(
        r"(IC50|EC50|EC90|Ki|Kd|IC90)\s*[=:]\s*([<>]?\d+\.?\d*)\s*(nM|µM|uM|μM|mM|pM|μM)",
        re.IGNORECASE,
    ),
    # Ki of 3.4 nM
    re.compile(
        r"(IC50|EC50|EC90|Ki|Kd|IC90)\s+of\s+([<>]?\d+\.?\d*)\s*(nM|µM|uM|μM|mM|pM|μM)",
        re.IGNORECASE,
    ),
    # 5.2 nM (IC50)
    re.compile(
        r"([<>]?\d+\.?\d*)\s*(nM|µM|uM|μM|mM|pM|μM)\s*\(?\s*(IC50|EC50|EC90|Ki|Kd|IC90)\s*\)?",
        re.IGNORECASE,
    ),
]

# 细胞系 / 靶点
_CELL_LINE_PATTERN = re.compile(
    r"(\b[A-Z][a-zA-Z0-9\-]+\s+(cell|cells|line)\b)",
    re.IGNORECASE,
)

# 酶 / 受体名称（简单启发式）
_TARGET_PATTERN = re.compile(
    r"(\b[A-Z][a-z]+\s+(receptor|kinase|protease|enzyme|channel|transporter)\b)",
    re.IGNORECASE,
)


class AssociationEngine:
    """分子图像-文本关联引擎."""

    def __init__(self) -> None:
        """初始化关联引擎."""
        pass

    def associate_all(
        self,
        results: List[ExtractionResult],
    ) -> List[ExtractionResult]:
        """批量关联：为每个 ExtractionResult 解析上下文文本.

        Args:
            results: 待关联的 ExtractionResult 列表

        Returns:
            已填充 name / properties 的结果列表（原地修改）
        """
        for result in results:
            self.associate_single(result)
        return results

    def associate_single(self, result: ExtractionResult) -> ExtractionResult:
        """为单个结果解析上下文.

        Args:
            result: 待关联的 ExtractionResult

        Returns:
            已填充的 ExtractionResult（原地修改）
        """
        text = result.context_text
        if not text:
            return result

        # 1. 提取化合物名称 / 编号
        name = self._extract_compound_name(text)
        if name and not result.name:
            result.name = name

        # 2. 提取活性数据
        activities = self._extract_activities(text)
        if activities:
            # 取第一个活性数据作为代表
            act_type, act_value, act_unit = activities[0]
            result.properties.setdefault("activity_type", act_type.upper())
            result.properties.setdefault("activity_value", act_value)
            result.properties.setdefault("activity_unit", act_unit)
            # 保存所有活性数据
            result.properties["activities"] = [
                {"type": t.upper(), "value": v, "unit": u}
                for t, v, u in activities
            ]

        # 3. 提取细胞系
        cell_lines = _CELL_LINE_PATTERN.findall(text)
        if cell_lines:
            result.properties.setdefault(
                "cell_lines",
                [c[0] for c in cell_lines],
            )

        # 4. 提取靶点
        targets = _TARGET_PATTERN.findall(text)
        if targets:
            result.properties.setdefault(
                "targets",
                [t[0] for t in targets],
            )

        return result

    def _extract_compound_name(self, text: str) -> Optional[str]:
        """从文本中提取化合物编号 / 名称.

        优先级：Compound > Fig > Scheme > Table
        """
        for pattern in _COMPOUND_NAME_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(0)
        return None

    def _extract_activities(
        self, text: str
    ) -> List[Tuple[str, float, str]]:
        """从文本中提取活性数据.

        Returns:
            [(activity_type, value, unit), ...]
        """
        activities: List[Tuple[str, float, str]] = []
        seen: set = set()

        for pattern in _ACTIVITY_PATTERNS:
            for match in pattern.finditer(text):
                # 根据模式不同，group 位置不同
                groups = match.groups()
                if len(groups) != 3:
                    continue

                # 判断哪个 group 是 type、value、unit
                g0, g1, g2 = groups
                if self._looks_like_type(g0):
                    act_type, val_str, unit = g0, g1, g2
                elif self._looks_like_type(g2):
                    act_type, val_str, unit = g2, g0, g1
                else:
                    continue

                try:
                    # 处理 < 或 > 前缀
                    val_clean = val_str.lstrip("<>").strip()
                    value = float(val_clean)
                except ValueError:
                    continue

                # 统一单位
                unit = self._normalize_unit(unit)
                key = (act_type.upper(), value, unit)
                if key not in seen:
                    seen.add(key)
                    activities.append((act_type, value, unit))

        return activities

    @staticmethod
    def _looks_like_type(s: str) -> bool:
        """判断字符串是否像活性类型（IC50, EC50 等）."""
        return s.upper() in {"IC50", "EC50", "EC90", "KI", "KD", "IC90"}

    @staticmethod
    def _normalize_unit(unit: str) -> str:
        """统一浓度单位."""
        u = unit.lower()
        if u in ("um", "μm", "μM"):
            return "µM"
        if u == "nm":
            return "nM"
        if u == "mm":
            return "mM"
        if u == "pm":
            return "pM"
        return unit
