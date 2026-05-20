"""工作流基类."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class WorkflowResult:
    """工作流执行结果."""

    success: bool = True
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)  # 输出文件路径


class WorkflowBase(ABC):
    """分子工作流基类."""

    name: str = "base"
    description: str = ""
    enabled: bool = False

    @abstractmethod
    def run(self, input_data: Dict[str, Any], **kwargs) -> WorkflowResult:
        """执行工作流."""
        ...

    @abstractmethod
    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, str]:
        """验证输入数据."""
        ...

    def get_config_schema(self) -> Dict[str, Any]:
        """返回配置 JSON Schema."""
        return {}
