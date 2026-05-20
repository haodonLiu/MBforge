"""分子对接工作流（预留）."""

from __future__ import annotations

from typing import Any, Dict

from .base import WorkflowBase, WorkflowResult


class DockingWorkflow(WorkflowBase):
    """分子对接工作流.

    预留接口，后续可集成：
    - AutoDock Vina
    - GNINA (GPU 加速对接)
    - LeDock
    """

    name = "docking"
    description = "分子-蛋白对接计算"

    def run(self, input_data: Dict[str, Any], **kwargs) -> WorkflowResult:
        return WorkflowResult(
            success=False,
            message="分子对接功能尚未实现。预留接口。",
        )

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, str]:
        if "protein" not in input_data:
            return False, "需要提供蛋白结构文件"
        if "ligands" not in input_data:
            return False, "需要提供配体列表"
        return True, ""
