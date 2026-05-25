"""插件基类与接口定义.

所有 MBForge 插件必须继承 BasePlugin，并实现以下至少一个能力:
- AGENT_TOOL: 向 Agent 注册工具（如分子对接、FEP计算）
- UI_PANEL:   向主窗口添加 Dock/Panel
- WORKFLOW:   提供批处理工作流步骤
- CLI_COMMAND: 提供 CLI 子命令
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, TYPE_CHECKING
from collections.abc import Callable

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget
    from ..agent.tools import ToolRegistry


class PluginCapability(Enum):
    """插件能力标志."""

    AGENT_TOOL = auto()   # 向 ReAct Agent 注册工具
    UI_PANEL = auto()     # 提供 Qt DockWidget / Panel
    WORKFLOW = auto()     # 提供批处理工作流步骤
    CLI_COMMAND = auto()  # 提供 CLI 子命令
    MOLECULE_IO = auto()  # 支持额外的分子文件格式读写


@dataclass
class PluginMetadata:
    """插件元数据 —— 每个插件必须提供."""

    name: str                          # 插件唯一标识（如 "cadd_template"）
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    requires: list[str] = field(default_factory=list)  # 依赖的其他插件名
    capabilities: list[PluginCapability] = field(default_factory=list)
    # CADD 专用：支持的计算引擎/软件
    supported_engines: list[str] = field(default_factory=list)
    # 外部可执行文件要求 ("vina", "gmx", "amber", ...)
    external_binaries: list[str] = field(default_factory=list)


@dataclass
class WorkflowStep:
    """工作流步骤描述 —— 供批处理流水线使用."""

    name: str
    description: str
    # 输入schema: {参数名: {type, description, required, default}}
    input_schema: dict[str, Any]
    # 输出schema
    output_schema: dict[str, Any]
    # 实际执行函数
    run: Callable[..., Any]


class BasePlugin(ABC):
    """MBForge 插件基类.

    子类必须:
      1. 定义 meta: PluginMetadata 类属性
      2. 实现 setup() 方法
      3. 根据需要实现 register_tools() / create_ui_panel() / get_workflow_steps()
    """

    meta: PluginMetadata

    # ---- 生命周期 ----

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root
        self._initialized = False

    def setup(self) -> None:
        """初始化插件 —— 检查外部依赖、创建缓存目录等.

        抛出 PluginSetupError 表示初始化失败，插件将被禁用。
        """
        self._initialized = True

    def teardown(self) -> None:  # noqa: B027
        """清理资源 —— 应用退出时调用.

        子类按需覆盖，默认空操作。
        """
        ...

    # ---- 能力接口（按需实现） ----

    def register_tools(self, registry: ToolRegistry) -> None:  # noqa: B027
        """【AGENT_TOOL】向 Agent 工具注册表注册工具.

        子类按需覆盖，默认空操作。

        示例:
            registry.register(
                name="docking",
                description="分子对接",
                parameters_schema={"ligand": {"type": "string"}, ...},
                func=self.run_docking,
            )
        """
        ...

    def create_ui_panel(self, parent: QWidget) -> QWidget | None:
        """【UI_PANEL】创建并返回 Qt 面板实例.

        返回 None 表示当前环境下不提供 UI（如 headless 模式）。
        """
        return None

    def get_workflow_steps(self) -> list[WorkflowStep]:
        """【WORKFLOW】返回该插件提供的工作流步骤列表."""
        return []

    def register_cli(self, subparsers: Any) -> None:  # noqa: B027
        """【CLI_COMMAND】注册 argparse subparser.

        子类按需覆盖，默认空操作。

        示例:
            p = subparsers.add_parser("docking", help="分子对接")
            p.add_argument("--receptor", required=True)
            p.set_defaults(func=self.cli_docking)
        """
        ...

    def supports_engine(self, engine: str) -> bool:
        """检查是否支持指定计算引擎."""
        return engine in self.meta.supported_engines

    # ---- 工具方法 ----

    def cache_dir(self) -> Path:
        """获取插件专属缓存目录."""
        if self.project_root is None:
            raise RuntimeError("project_root not set")
        path = self.project_root / ".mbforge" / "plugin_cache" / self.meta.name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def check_binary(self, name: str) -> Path | None:
        """检查外部可执行文件是否在 PATH 中."""
        import shutil
        exe = shutil.which(name)
        return Path(exe) if exe else None

    def require_binary(self, *names: str) -> None:
        """要求外部可执行文件必须存在，否则抛出 PluginSetupError."""
        missing = [n for n in names if not self.check_binary(n)]
        if missing:
            raise PluginSetupError(
                f"插件 {self.meta.name} 需要外部程序: {', '.join(missing)}"
            )


class PluginSetupError(Exception):
    """插件初始化失败."""

    pass
