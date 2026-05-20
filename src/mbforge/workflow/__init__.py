"""MBForge 分子工作流模块.

预留扩展接口：
- 分子生成 (Generation)
- 分子对接 (Docking)
- QSAR 建模
- 分子动力学 (MD)
"""

from .base import WorkflowBase, WorkflowResult
from .generation import GenerationWorkflow
from .docking import DockingWorkflow
from .qsar import QSARWorkflow
from .md import MDWorkflow

__all__ = [
    "WorkflowBase",
    "WorkflowResult",
    "GenerationWorkflow",
    "DockingWorkflow",
    "QSARWorkflow",
    "MDWorkflow",
]
