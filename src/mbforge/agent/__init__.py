"""MBForge Agent 框架.

轻量级 LLM Agent，不依赖 LangChain：
- 分层上下文管理
- Function Calling 工具调用
- ReAct 推理循环
"""

from .agent import ProjectAgent
from .archive_agent import ArchiveAgent
from .context import LayeredContext
from .executor import ToolExecutor
from .memory_manager import MemoryManager, MemoryEntry
from .tools import ToolRegistry, tool
from .trajectory import TrajectoryTracker, TrajectoryStep

__all__ = [
    "ProjectAgent",
    "ArchiveAgent",
    "LayeredContext",
    "ToolExecutor",
    "ToolRegistry",
    "tool",
    "MemoryManager",
    "MemoryEntry",
    "TrajectoryTracker",
    "TrajectoryStep",
]
