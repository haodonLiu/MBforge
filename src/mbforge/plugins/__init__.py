"""MBForge 插件系统 —— 可扩展的 CADD/计算化学工作流接口.

使用方式:
    from mbforge.plugins import PluginRegistry, BasePlugin

    # 注册内置插件
    registry = PluginRegistry()
    registry.discover()

    # 获取插件实例
    plugin = registry.get("cadd_template")
    plugin.run_docking(mol, receptor_pdb)
"""

from __future__ import annotations

from .base import BasePlugin, PluginMetadata, PluginCapability
from .registry import PluginRegistry

__all__ = [
    "BasePlugin",
    "PluginMetadata",
    "PluginCapability",
    "PluginRegistry",
]
