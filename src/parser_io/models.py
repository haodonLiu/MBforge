"""数据模型定义."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ParseResult:
    """UniParser 返回的原始结果.

    Attributes:
        status: 解析状态，如 "success", "error"
        token: 解析任务的唯一标识符
        raw_data: 原始返回数据
    """

    status: str
    token: str
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MoleculeData:
    """提取的分子数据，供 openSAR 使用。

    Attributes:
        smiles: 分子的 SMILES 字符串
        name: 分子名称
        activity: 活性值（如 IC50），单位应为 nM
        source: 来源位置描述
    """

    smiles: str
    name: str
    activity: Optional[float] = None
    source: str = ""


@dataclass
class SARTask:
    """SAR 分析任务.

    Attributes:
        molecules: 分子数据列表
        metadata: 任务元信息
    """

    molecules: List[MoleculeData] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
