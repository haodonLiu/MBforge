"""MBForge 工具注册与执行框架.

保留模块：ToolExecutor（被 Rust Agent 用作 sidecar 工具桥接）。
已移除：ProjectAgent, LayeredContext（迁移到 Rust 端）。
"""

from __future__ import annotations

from .tools import ToolInfo, ToolMixin, ToolRegistry, tool
from .executor import ToolExecutor

__all__ = [
    "ToolExecutor",
    "ToolRegistry",
    "ToolInfo",
    "tool",
    "ToolMixin",
]
