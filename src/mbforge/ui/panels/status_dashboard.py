"""状态仪表盘组件（资源监控部分）."""

from __future__ import annotations


from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QWidget,
)

from ..components import InfoRow
from ..theme import CardWidget


class StatusDashboard(QWidget):
    """资源监控卡片（已移至状态栏）."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMaximumHeight(60)
        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.setInterval(5000)
        self._timer.start()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        res_card = CardWidget("资源监控")
        self.cpu_info = InfoRow("CPU", "-")
        self.memory_info = InfoRow("内存", "-")
        res_card.add_widget(self.cpu_info)
        res_card.add_widget(self.memory_info)
        layout.addWidget(res_card)

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

    def set_service_status(self, **kwargs):
        """空实现，保留接口兼容。"""
        pass
