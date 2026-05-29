"""MBForge Agent 框架.

轻量级 LLM Agent，不依赖 LangChain：
- 分层上下文管理
- Function Calling 工具调用
- ReAct 推理循环
"""

from __future__ import annotations

__all__ = [
    "ProjectAgent",
    "ArchiveAgent",
    "LayeredContext",
    "ToolExecutor",
    "ToolRegistry",
    "tool",
]
