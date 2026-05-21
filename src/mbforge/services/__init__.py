"""services — 应用服务层.

负责资源生命周期管理，解耦 UI 层与底层模块。
"""

from .app_context import AppContext

__all__ = ["AppContext"]
