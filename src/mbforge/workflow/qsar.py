"""QSAR 建模工作流（预留）."""

from __future__ import annotations

from typing import Any, Dict

from .base import WorkflowBase, WorkflowResult


class QSARWorkflow(WorkflowBase):
    """QSAR 建模工作流.

    预留接口，后续可集成：
    - 传统机器学习（RF, SVM, XGBoost）
    - 图神经网络（GNN）
    - 分子指纹 + 深度学习
    """

    name = "qsar"
    description = "定量构效关系建模"

    def run(self, input_data: Dict[str, Any], **kwargs) -> WorkflowResult:
        return WorkflowResult(
            success=False,
            message="QSAR 功能尚未实现。预留接口。",
        )

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, str]:
        if "molecules" not in input_data:
            return False, "需要提供分子数据集"
        if "target" not in input_data:
            return False, "需要指定目标性质"
        return True, ""
