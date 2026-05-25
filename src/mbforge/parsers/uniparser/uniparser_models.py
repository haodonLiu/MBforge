"""数据模型定义.

定义 Parser IO 模块的核心数据类型，用于 UniParser 返回结果的结构化表示。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParseResult:
    """UniParser 返回的原始结果.

    Attributes:
        status: 解析状态，如 "success", "error"
        token: 解析任务的唯一标识符，用于获取结果
        raw_data: 原始返回数据
    """

    status: str
    token: str
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class MoleculeData:
    """提取的分子数据，供 openSAR 使用。

    Attributes:
        smiles: 分子的 SMILES 字符串
        name: 分子名称
        activity: 活性值（如 IC50），单位应为 nM
        source: 来源位置描述，如 "page 5, figure 3"
    """

    smiles: str
    name: str
    activity: float | None = None
    source: str = ""


@dataclass
class SARTask:
    """SAR 分析任务.

    包含一组分子数据及其元信息，可直接传递给 openSAR 进行分析。

    Attributes:
        molecules: 分子数据列表
        metadata: 任务元信息，如来源文件、解析时间等
    """

    molecules: list[MoleculeData] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
