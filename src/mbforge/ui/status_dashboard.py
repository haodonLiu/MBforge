"""状态仪表盘组件."""

from __future__ import annotations

import platform
from typing import Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QWidget,
)

from .components import InfoRow, StatusBadge
from .theme import CardWidget


class StatusDashboard(QWidget):
    """系统状态仪表盘：展示 LLM / Embedding / 数据库连接状态和资源监控."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMaximumHeight(200)
        self._setup_ui()

        # 定时刷新
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.setInterval(5000)
        self._timer.start()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 服务状态卡片
        services_card = CardWidget("服务状态")
        self.llm_badge = StatusBadge("LLM", "offline")
        self.embed_badge = StatusBadge("Embedding", "offline")
        self.kb_badge = StatusBadge("知识库", "offline")
        self.mol_db_badge = StatusBadge("分子库", "offline")

        services_layout = QHBoxLayout()
        services_layout.setSpacing(8)
        services_layout.addWidget(self.llm_badge)
        services_layout.addWidget(self.embed_badge)
        services_layout.addWidget(self.kb_badge)
        services_layout.addWidget(self.mol_db_badge)
        services_layout.addStretch()
        services_card.add_layout(services_layout)
        layout.addWidget(services_card)

        # 系统信息卡片
        sys_card = CardWidget("系统信息")
        self.platform_info = InfoRow("平台", f"{platform.system()} {platform.release()}")
        self.python_info = InfoRow("Python", platform.python_version())
        sys_card.add_widget(self.platform_info)
        sys_card.add_widget(self.python_info)
        layout.addWidget(sys_card)

        # 资源监控卡片
        res_card = CardWidget("资源监控")
        self.cpu_info = InfoRow("CPU", "-")
        self.memory_info = InfoRow("内存", "-")
        res_card.add_widget(self.cpu_info)
        res_card.add_widget(self.memory_info)
        layout.addWidget(res_card)

    def set_service_status(
        self,
        llm: Optional[bool] = None,
        embed: Optional[bool] = None,
        kb: Optional[bool] = None,
        mol_db: Optional[bool] = None,
    ):
        """更新服务状态."""
        if llm is not None:
            self.llm_badge.set_status("online" if llm else "offline")
        if embed is not None:
            self.embed_badge.set_status("online" if embed else "offline")
        if kb is not None:
            self.kb_badge.set_status("online" if kb else "offline")
        if mol_db is not None:
            self.mol_db_badge.set_status("online" if mol_db else "offline")

    def refresh(self):
        """刷新资源监控数据."""
        try:
            import psutil

            cpu_percent = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            self.cpu_info.set_value(f"{cpu_percent:.1f}%")
            self.memory_info.set_value(
                f"{mem.used // (1024**3)}G / {mem.total // (1024**3)}G ({mem.percent:.0f}%)"
            )
        except ImportError:
            self.cpu_info.set_value("未安装 psutil")
            self.memory_info.set_value("-")
        except Exception:
            pass
