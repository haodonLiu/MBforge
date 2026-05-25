"""可复用自定义 UI 组件.

提供项目通用的复合组件，减少重复代码。
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .theme import (
    FONT_SIZE_DEFAULT,
    FONT_SIZE_SMALL,
    RADIUS_DEFAULT,
    RADIUS_LARGE,
    ThemeManager,
    create_button,
    create_label,
)


class IconButton(QPushButton):
    """紧凑型图标按钮，无边框背景，悬浮显底."""

    def __init__(self, icon_text: str, tooltip: str = "", parent: Optional[QWidget] = None):
        super().__init__(icon_text, parent)
        self.setToolTip(tooltip)
        p = ThemeManager.instance().palette()
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {p['text_secondary']};
                border: none;
                border-radius: {RADIUS_DEFAULT};
                padding: 4px 8px;
                font-size: {FONT_SIZE_DEFAULT};
            }}
            QPushButton:hover {{
                background: {p['bg_hover']};
                color: {p['text_primary']};
            }}
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class StatusBadge(QLabel):
    """状态徽章标签，显示在线/离线/处理中等状态."""

    def __init__(self, text: str = "", status: str = "offline", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_status(status)

    def set_status(self, status: str) -> None:
        self._status = status if status in ("online", "offline", "warning", "error", "processing") else "offline"
        p = ThemeManager.instance().palette()
        colors = {
            "online": (p["success"], "#ffffff"),
            "offline": (p["text_secondary"], "#ffffff"),
            "warning": (p["accent_amber"], "#212529"),
            "error": (p["accent_coral"], "#ffffff"),
            "processing": (p["brand_primary"], "#ffffff"),
        }
        bg, fg = colors.get(self._status, colors["offline"])
        self.setStyleSheet(f"QLabel {{ background: {bg}; color: {fg}; padding: 2px 8px; border-radius: 10px; font-size: 11px; }}")


class SectionHeader(QWidget):
    """分节标题组件：左侧标题文字 + 右侧可选操作按钮."""

    def __init__(
        self,
        title: str,
        action_text: str = "",
        action_callback: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.title_label = create_label(title, level="header")
        layout.addWidget(self.title_label)
        layout.addStretch()

        if action_text and action_callback:
            self.action_btn = create_button(action_text, style="default")
            self.action_btn.clicked.connect(action_callback)
            layout.addWidget(self.action_btn)


class EmptyStateWidget(QWidget):
    """空状态提示组件，用于列表/表格为空时展示."""

    def __init__(self, icon: str = "📭", title: str = "暂无数据",
                 subtitle: str = "", action_text: str = "",
                 action_callback: Optional[Callable[[], None]] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        p = ThemeManager.instance().palette()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)
        icon_label = QLabel(icon, parent)
        icon_label.setStyleSheet("font-size: 48px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        title_label = QLabel(title, parent)
        title_label.setStyleSheet(f"color: {p['text_primary']}; font-size: 16px; font-weight: 600;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        if subtitle:
            sub_label = QLabel(subtitle, parent)
            sub_label.setStyleSheet(f"color: {p['text_secondary']}; font-size: 13px;")
            sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(sub_label)
        if action_text and action_callback:
            from ..ui.theme import create_button
            btn = create_button(action_text, style="primary")
            btn.clicked.connect(action_callback)
            layout.addWidget(btn)


class LoadingSpinner(QWidget):
    """简易加载动画（使用 QLabel + 文本动画，不依赖外部 GIF）."""

    def __init__(self, text: str = "加载中", parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        self._dots = 0
        self._base_text = text
        self.label = create_label(text, level="body")
        layout.addWidget(self.label)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.setInterval(500)

    def start(self) -> None:
        self.setVisible(True)
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.setVisible(False)

    def _animate(self) -> None:
        self._dots = (self._dots + 1) % 4
        self.label.setText(self._base_text + "." * self._dots)


class ProgressBar(QProgressBar):
    """统一风格的进度条."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setTextVisible(True)
        self.setMaximumHeight(14)
        p = ThemeManager.instance().palette()
        self.setStyleSheet(f"""
            QProgressBar {{
                background: {p['bg_hover']};
                border: none;
                border-radius: 4px;
                text-align: center;
                font-size: {FONT_SIZE_SMALL};
            }}
            QProgressBar::chunk {{
                background: {p['brand_primary']};
                border-radius: 4px;
            }}
        """)


class ToolBar(QWidget):
    """简洁工具栏，替代 QToolBar，避免与全局样式冲突."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        p = ThemeManager.instance().palette()
        self.setStyleSheet(f"""
            QWidget {{
                background: {p['bg_secondary']};
                border-bottom: 1px solid {p['border']};
            }}
        """)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(10, 6, 10, 6)
        self._layout.setSpacing(6)

    def add_button(self, text: str, callback: Callable[[], None], style: str = "default") -> QPushButton:
        btn = create_button(text, style=style)
        btn.clicked.connect(callback)
        self._layout.addWidget(btn)
        return btn

    def add_icon_button(self, icon_text: str, tooltip: str, callback: Callable[[], None]) -> IconButton:
        btn = IconButton(icon_text, tooltip)
        btn.clicked.connect(callback)
        self._layout.addWidget(btn)
        return btn

    def add_stretch(self) -> None:
        self._layout.addStretch()

    def add_separator(self) -> None:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        p = ThemeManager.instance().palette()
        sep.setStyleSheet(f"color: {p['border']};")
        sep.setFixedWidth(1)
        self._layout.addWidget(sep)


class InfoRow(QWidget):
    """键值对信息行，用于详情展示."""

    def __init__(self, key: str, value: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        p = ThemeManager.instance().palette()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(12)
        self.key_label = QLabel(f"{key}:", parent)
        self.key_label.setStyleSheet(f"color: {p['text_secondary']}; font-size: 12px;")
        self.key_label.setMinimumWidth(80)
        layout.addWidget(self.key_label)
        self.value_label = QLabel(value, parent)
        self.value_label.setStyleSheet(f"color: {p['text_primary']}; font-size: 13px;")
        self.value_label.setWordWrap(True)
        layout.addWidget(self.value_label, 1)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)
