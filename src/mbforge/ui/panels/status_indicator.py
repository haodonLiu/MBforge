"""服务状态指示器：右上角 4 个圆点，hover 显示详情."""

from __future__ import annotations


from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ..theme import ThemeManager


class ServiceStatusIndicator(QWidget):
    """右上角 4 个服务状态圆点，hover 显示详情."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._status = {
            "LLM": "offline",
            "Embedding": "offline",
            "知识库": "offline",
            "分子库": "offline",
        }
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._dots = {}
        p = ThemeManager.instance().palette()
        initial_color = p["text_secondary"]
        for name in ["LLM", "Embedding", "知识库", "分子库"]:
            dot = QLabel("●")
            dot.setStyleSheet(f"font-size: 12px; color: {initial_color};")
            dot.setToolTip(f"{name}: 未连接")
            self._dots[name] = dot
            layout.addWidget(dot)

    def set_status(self, name: str, online: bool):
        """更新单个服务状态."""
        self._status[name] = "online" if online else "offline"
        self._update_dot(name)

    def _update_dot(self, name: str):
        p = ThemeManager.instance().palette()
        if self._status[name] == "online":
            color = p["success"]
        else:
            color = p["text_secondary"]
        self._dots[name].setStyleSheet(f"font-size: 12px; color: {color};")
        status_text = "在线" if self._status[name] == "online" else "离线"
        self._dots[name].setToolTip(f"{name}: {status_text}")

    def get_tooltip(self) -> str:
        """生成完整悬停提示文本."""
        lines = []
        for name, status in self._status.items():
            status_text = "在线" if status == "online" else "离线"
            lines.append(f"{name}: {status_text}")
        return "\n".join(lines)
