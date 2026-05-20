"""分子生成工作流（预留）."""

from __future__ import annotations

from typing import Any, Dict

from .base import WorkflowBase, WorkflowResult


class GenerationWorkflow(WorkflowBase):
    """基于 AI 的分子生成.

    预留接口，后续可集成：
    - RNN/LSTM/Transformer 生成模型
    - 强化学习分子优化
    - 扩散模型（Diffusion Models）
    """

    name = "generation"
    description = "基于 AI 的分子生成与优化"

    def run(self, input_data: Dict[str, Any], **kwargs) -> WorkflowResult:
        return WorkflowResult(
            success=False,
            message="分子生成功能尚未实现。预留接口。",
        )

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, str]:
        if "scaffold" not in input_data and "constraints" not in input_data:
            return False, "需要提供 scaffold 或 constraints"
        return True, ""
