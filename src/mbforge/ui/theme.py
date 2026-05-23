"""UI 主题管理器与通用样式常量.

集中管理全局 QSS 与配色，消除各 widget 中重复的内联样式。
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

# ---------- Palette: Light Mode ----------
LIGHT_PALETTE = {
    "brand_primary": "#0F4C81",
    "brand_primary_light": "#3D5A80",
    "brand_primary_deep": "#0A3A62",
    "accent_amber": "#F4A261",
    "accent_coral": "#E76F51",
    "success": "#2A9D8F",
    "bg_base": "#F7F9FC",
    "bg_card": "#FFFFFF",
    "bg_hover": "#EDF2F7",
    "bg_zebra": "#F0F4F8",
    "text_primary": "#1D3557",
    "text_secondary": "#7A8A9C",
    "border": "#E9ecef",
    "border_focus": "#0F4C81",
}

# ---------- Palette: Dark Mode ----------
DARK_PALETTE = {
    "brand_primary": "#4A90D9",
    "brand_primary_light": "#6BA3D6",
    "brand_primary_deep": "#1D3557",
    "accent_amber": "#F4A261",
    "accent_coral": "#E76F51",
    "success": "#2A9D8F",
    "bg_base": "#0F1419",
    "bg_card": "#1A1F26",
    "bg_hover": "#2A3441",
    "bg_zebra": "#1A2430",
    "text_primary": "#E8EDF2",
    "text_secondary": "#6B7A8C",
    "border": "#2A3441",
    "border_focus": "#4A90D9",
}

# ---------- 尺寸常量 ----------
RADIUS_SMALL = "6px"
RADIUS_DEFAULT = "8px"
RADIUS_LARGE = "10px"
RADIUS_XL = "12px"
PADDING_SMALL = "4px 10px"
PADDING_DEFAULT = "6px 12px"
PADDING_BUTTON = "6px 16px"
FONT_SIZE_SMALL = "12px"
FONT_SIZE_DEFAULT = "13px"
FONT_SIZE_MEDIUM = "14px"


# ---------- Helper builder functions ----------
def _p() -> dict:
    """Get current palette from ThemeManager instance."""
    return ThemeManager.instance().palette()


def _build_button_styles(p: dict) -> tuple[str, str, str]:
    primary = f"""
    QPushButton {{
        background: {p['brand_primary']};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 6px 16px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background: {p['brand_primary_light']}; }}
    QPushButton:pressed {{ background: {p['brand_primary_deep']}; }}
    """
    default = f"""
    QPushButton {{
        background: {p['bg_hover']};
        color: {p['text_primary']};
        border: 1px solid {p['border']};
        border-radius: 6px;
        padding: 6px 16px;
    }}
    QPushButton:hover {{ background: {p['border']}; }}
    QPushButton:pressed {{ background: {p['border']}; }}
    """
    danger = f"""
    QPushButton {{
        background: {p['accent_coral']};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 6px 16px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background: #d4563e; }}
    """
    return primary, default, danger


def _build_global_qss() -> str:
    p = _p()
    return f"""
    QMainWindow {{ background: {p['bg_base']}; }}
    QWidget {{ background: {p['bg_base']}; color: {p['text_primary']}; }}
    QMenuBar {{
        background: {p['brand_primary_deep']};
        color: #ffffff;
        border-bottom: none;
        padding: 0 8px;
    }}
    QMenuBar::item {{ padding: 8px 14px; border-radius: 4px; color: #ffffff; }}
    QMenuBar::item:selected {{ background: rgba(255,255,255,0.15); }}
    QMenu {{
        background: {p['bg_card']};
        color: {p['text_primary']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        padding: 6px;
    }}
    QMenu::item {{ padding: 6px 20px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {p['bg_hover']}; }}
    QMenu::separator {{ height: 1px; background: {p['border']}; margin: 6px 12px; }}
    QStatusBar {{ background: {p['bg_base']}; color: {p['text_secondary']}; border-top: 1px solid {p['border']}; padding: 2px 12px; font-size: 12px; }}
    QSplitter::handle {{ background: {p['border']}; }}
    QSplitter::handle:horizontal {{ width: 2px; }}
    QLabel {{ color: {p['text_primary']}; }}
    """


def _build_dialog_qss() -> str:
    p = _p()
    return f"""
    QDialog {{ background: {p['bg_card']}; }}
    QLabel {{ color: {p['text_primary']}; }}
    QLineEdit {{
        background: {p['bg_base']};
        color: {p['text_primary']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        padding: 6px 12px;
    }}
    QLineEdit:focus {{ border-color: {p['border_focus']}; }}
    QTextEdit {{
        background: {p['bg_base']};
        color: {p['text_primary']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        padding: 6px 12px;
    }}
    QComboBox {{
        background: {p['bg_base']};
        color: {p['text_primary']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        padding: 6px 12px;
    }}
    QSpinBox, QDoubleSpinBox {{
        background: {p['bg_base']};
        color: {p['text_primary']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        padding: 6px 12px;
    }}
    QPushButton {{
        background: {p['bg_hover']};
        color: {p['text_primary']};
        border: 1px solid {p['border']};
        border-radius: 6px;
        padding: 6px 16px;
    }}
    QPushButton:hover {{ background: {p['border']}; }}
    """


class ThemeManager(QObject):
    """全局主题管理器 — 单例模式，持有当前调色板，主题变更时发射信号."""

    theme_changed = pyqtSignal(str)  # emits "light" or "dark"

    _instance: Optional["ThemeManager"] = None

    def __init__(self):
        super().__init__()
        self._palette: dict = LIGHT_PALETTE.copy()
        self._mode: str = "light"
        # Bind to system color scheme changes
        app = QGuiApplication.instance()
        if app:
            app.styleHints().colorSchemeChanged.connect(self._on_system_color_scheme_changed)

    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def mode(self) -> str:
        return self._mode

    def is_dark(self) -> bool:
        return self._mode == "dark"

    def palette(self) -> dict:
        return self._palette.copy()

    def get_color(self, key: str) -> str:
        return self._palette.get(key, "#000000")

    def set_mode(self, mode: str) -> None:
        if mode == "system":
            self._apply_system_mode()
        else:
            self._set_mode(mode)

    def _set_mode(self, mode: str) -> None:
        if mode == self._mode:
            return
        self._mode = mode
        self._palette = DARK_PALETTE.copy() if mode == "dark" else LIGHT_PALETTE.copy()
        self.theme_changed.emit(mode)

    def _on_system_color_scheme_changed(self) -> None:
        self._apply_system_mode()

    def _apply_system_mode(self) -> None:
        app = QGuiApplication.instance()
        if app:
            dark = app.styleHints().colorScheme() == 1  # Qt.ColorScheme.Dark = 1
            self._set_mode("dark" if dark else "light")

    @staticmethod
    def apply_global(widget: QWidget) -> None:
        widget.setStyleSheet(_build_global_qss())

    @staticmethod
    def apply_dialog(dialog: QWidget) -> None:
        dialog.setStyleSheet(_build_dialog_qss())


# ---------- 工厂函数 ----------


def create_button(
    text: str,
    style: str = "default",
    parent: Optional[QWidget] = None,
) -> QPushButton:
    """创建统一风格的按钮.

    Args:
        text: 按钮文字
        style: "default" | "primary" | "danger"
        parent: 父 widget
    """
    btn = QPushButton(text, parent)
    primary, default, danger = _build_button_styles(_p())
    if style == "primary":
        btn.setStyleSheet(primary)
    elif style == "danger":
        btn.setStyleSheet(danger)
    else:
        btn.setStyleSheet(default)
    return btn


def create_input(
    placeholder: str = "",
    password: bool = False,
    parent: Optional[QWidget] = None,
) -> QLineEdit:
    """创建统一风格的输入框.

    Args:
        placeholder: 占位符文字
        password: 是否为密码输入
        parent: 父 widget
    """
    p = _p()
    edit = QLineEdit(parent)
    edit.setPlaceholderText(placeholder)
    edit.setStyleSheet(f"""
    QLineEdit {{
        background: {p['bg_base']};
        color: {p['text_primary']};
        border: 1px solid {p['border']};
        border-radius: 20px;
        padding: 6px 16px;
        font-size: 13px;
    }}
    QLineEdit:focus {{
        border-color: {p['border_focus']};
        background: {p['bg_card']};
    }}
    """)
    if password:
        edit.setEchoMode(QLineEdit.EchoMode.Password)
    return edit


def create_label(
    text: str,
    level: str = "body",
    parent: Optional[QWidget] = None,
) -> QLabel:
    """创建统一风格的标签.

    Args:
        text: 标签文字
        level: "header" | "body" | "caption"
        parent: 父 widget
    """
    p = _p()
    label = QLabel(text, parent)
    if level == "header":
        label.setStyleSheet(f"QLabel {{ color: {p['text_primary']}; font-weight: 600; font-size: 14px; }}")
    elif level == "caption":
        label.setStyleSheet(f"QLabel {{ color: {p['text_secondary']}; font-size: 12px; }}")
    else:
        label.setStyleSheet(f"QLabel {{ color: {p['text_primary']}; font-size: 13px; }}")
    return label


def create_table(headers: list[str], parent: Optional[QWidget] = None) -> QTableWidget:
    """创建统一风格的表格.

    Args:
        headers: 表头列表
        parent: 父 widget
    """
    p = _p()
    table = QTableWidget(parent)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setStyleSheet(f"""
    QTableWidget {{
        background: {p['bg_card']};
        color: {p['text_primary']};
        gridline-color: {p['border']};
        border: 1px solid {p['border']};
        border-radius: 10px;
        outline: none;
    }}
    QHeaderView::section {{
        background: {p['bg_base']};
        color: {p['text_secondary']};
        padding: 8px 12px;
        border: 1px solid {p['border']};
        font-weight: 500;
        font-size: 12px;
    }}
    QTableWidget::item {{
        padding: 6px 10px;
    }}
    QTableWidget::item:selected {{
        background: {p['brand_primary']}1a;
        color: {p['brand_primary']};
    }}
    QTableWidget::item:hover {{
        background: {p['bg_hover']};
    }}
    """)
    return table


def create_tree(parent: Optional[QWidget] = None) -> QTreeWidget:
    """创建统一风格的树形组件."""
    p = _p()
    tree = QTreeWidget(parent)
    tree.setStyleSheet(f"""
    QTreeWidget {{
        border: none;
        background: {p['bg_base']};
        color: {p['text_primary']};
        outline: none;
    }}
    QTreeWidget::item {{
        padding: 4px 2px;
        border-radius: 4px;
    }}
    QTreeWidget::item:selected {{
        background: {p['brand_primary']}1a;
        color: {p['brand_primary']};
    }}
    QTreeWidget::item:hover {{
        background: {p['bg_hover']};
    }}
    """)
    return tree


class CardWidget(QFrame):
    """卡片容器组件，带圆角边框和标题."""

    def __init__(
        self,
        title: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        p = _p()
        self.setStyleSheet(f"""
        QFrame {{
            background: {p['bg_card']};
            border: 1px solid {p['border']};
            border-radius: 10px;
        }}
        """)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(8)

        if title:
            self._title_label = create_label(title, level="header")
            self._layout.addWidget(self._title_label)
        else:
            self._title_label = None

    def set_content(self, widget: QWidget) -> None:
        """设置卡片内容区域."""
        self._layout.addWidget(widget)

    def add_widget(self, widget: QWidget) -> None:
        """向卡片添加子 widget."""
        self._layout.addWidget(widget)

    def add_layout(self, layout: QHBoxLayout | QVBoxLayout) -> None:
        """向卡片添加子布局."""
        self._layout.addLayout(layout)


class SearchBox(QLineEdit):
    """带搜索图标的搜索输入框（替代输入框+按钮组合）."""

    def __init__(self, placeholder: str = "搜索...", parent: Optional[QWidget] = None):
        super().__init__(parent)
        p = _p()
        self.setPlaceholderText(f"🔍 {placeholder}")
        self.setStyleSheet(f"""
        QLineEdit {{
            background: {p['bg_base']};
            color: {p['text_primary']};
            border: 1px solid {p['border']};
            border-radius: 20px;
            padding: 6px 16px 6px 32px;
            font-size: 13px;
        }}
        QLineEdit:focus {{
            border-color: {p['border_focus']};
            background: {p['bg_card']};
        }}
        """)
        self.setMinimumHeight(32)
