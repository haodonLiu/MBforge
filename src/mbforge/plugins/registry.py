"""插件注册表 —— 发现、加载和管理插件.

支持两种发现机制:
1. 内置插件: src/mbforge/plugins/ 下的子目录
2. 外部插件: Python entry_points (mbforge.plugins)
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from pathlib import Path

from .base import BasePlugin, PluginCapability, PluginSetupError
from ..agent.tools import ToolRegistry


class PluginRegistry:
    """插件注册表 —— 单例模式."""

    _instance: PluginRegistry | None = None

    def __new__(cls) -> PluginRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._plugins: dict[str, BasePlugin] = {}
            cls._instance._plugin_classes: dict[str, type[BasePlugin]] = {}
        return cls._instance

    # ---- 发现与加载 ----

    def discover(self, project_root: Path | None = None) -> None:
        """自动发现所有可用插件.

        搜索路径:
        1. mbforge.plugins 包内的子模块
        2. sys.path 中通过 entry_points 注册的外部插件
        """
        self._discover_builtin(project_root)
        self._discover_entry_points(project_root)

    def _discover_builtin(self, project_root: Path | None) -> None:
        """发现内置插件（mbforge/plugins/ 下的子目录）."""
        from .. import plugins as plugins_pkg

        pkg_path = Path(plugins_pkg.__path__[0])  # type: ignore
        for _, name, ispkg in pkgutil.iter_modules([str(pkg_path)]):
            if not ispkg or name in ("base", "registry"):
                continue
            try:
                mod = importlib.import_module(f"mbforge.plugins.{name}")
                self._load_from_module(mod, name, project_root)
            except Exception as e:
                print(f"[PluginRegistry] 跳过插件 {name}: {e}")

    def _discover_entry_points(self, project_root: Path | None) -> None:
        """通过 entry_points 发现外部插件."""
        try:
            from importlib.metadata import entry_points
        except ImportError:
            return

        eps = entry_points()
        if hasattr(eps, "select"):
            group = eps.select(group="mbforge.plugins")
        else:
            group = eps.get("mbforge.plugins", [])

        for ep in group:
            try:
                plugin_class = ep.load()
                self._register_class(ep.name, plugin_class, project_root)
            except Exception as e:
                print(f"[PluginRegistry] 外部插件 {ep.name} 加载失败: {e}")

    def _load_from_module(
        self, mod, name: str, project_root: Path | None
    ) -> None:
        """从模块中查找 BasePlugin 子类并注册."""
        for obj_name, obj in inspect.getmembers(mod, inspect.isclass):
            if (
                issubclass(obj, BasePlugin)
                and obj is not BasePlugin
                and not obj_name.startswith("_")
            ):
                self._register_class(name, obj, project_root)
                break

    def _register_class(
        self, name: str, plugin_class: type[BasePlugin], project_root: Path | None
    ) -> None:
        """注册插件类（不实例化）."""
        meta = getattr(plugin_class, "meta", None)
        if meta is None:
            raise PluginSetupError(f"{plugin_class.__name__} 缺少 meta 属性")
        self._plugin_classes[meta.name] = plugin_class
        # 立即实例化并初始化
        instance = plugin_class(project_root=project_root)
        instance.setup()
        self._plugins[meta.name] = instance
        print(f"[PluginRegistry] 已加载插件: {meta.name} v{meta.version}")

    # ---- 查询 ----

    def get(self, name: str) -> BasePlugin | None:
        """按名称获取插件实例."""
        return self._plugins.get(name)

    def list_all(self) -> list[str]:
        """返回所有已加载插件名称."""
        return list(self._plugins.keys())

    def list_by_capability(self, capability: PluginCapability) -> list[BasePlugin]:
        """返回具备指定能力的插件列表."""
        return [
            p for p in self._plugins.values() if capability in p.meta.capabilities
        ]

    def get_tools_registry(self, tool_registry: ToolRegistry) -> None:
        """将所有 AGENT_TOOL 能力的插件工具注册到 Agent."""
        for plugin in self.list_by_capability(PluginCapability.AGENT_TOOL):
            plugin.register_tools(tool_registry)

    def create_panels(self, parent):
        """创建所有 UI_PANEL 能力的插件面板 (保留兼容，新架构不使用 Qt)."""
        panels = {}
        for plugin in self.list_by_capability(PluginCapability.UI_PANEL):
            panel = plugin.create_ui_panel(parent)
            if panel is not None:
                panels[plugin.meta.name] = panel
        return panels

    def get_all_workflow_steps(self) -> dict[str, list]:
        """收集所有 WORKFLOW 能力的插件步骤."""
        result: dict[str, list] = {}
        for plugin in self.list_by_capability(PluginCapability.WORKFLOW):
            result[plugin.meta.name] = plugin.get_workflow_steps()
        return result

    # ---- 生命周期 ----

    def teardown_all(self) -> None:
        """关闭所有插件."""
        for plugin in self._plugins.values():
            plugin.teardown()
        self._plugins.clear()
        self._plugin_classes.clear()
