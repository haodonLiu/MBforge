"""分子动力学工作流（预留）."""

from __future__ import annotations

from typing import Any, Dict

from .base import WorkflowBase, WorkflowResult


class MDWorkflow(WorkflowBase):
    """分子动力学模拟工作流.

    预留接口，后续可集成：
    - GROMACS
    - AMBER
    - OpenMM
    """

    name = "md"
    description = "分子动力学模拟"

    def run(self, input_data: Dict[str, Any], **kwargs) -> WorkflowResult:
        return WorkflowResult(
            success=False,
            message="MD 功能尚未实现。预留接口。",
        )

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, str]:
        if "structure" not in input_data:
            return False, "需要提供分子结构文件"
        return True, ""
