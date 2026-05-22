"""UI 主题管理器与通用样式常量.

集中管理全局 QSS 与配色，消除各 widget 中重复的内联样式。
"""

from __future__ import annotations

from typing import Optional

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

# ---------- 颜色常量 ----------
COLOR_PRIMARY = "#1971c2"
COLOR_PRIMARY_HOVER = "#1864ab"
COLOR_PRIMARY_PRESSED = "#1565c0"
COLOR_DANGER = "#fa5252"
COLOR_DANGER_HOVER = "#f03e3e"
COLOR_BG_MAIN = "#ffffff"
COLOR_BG_SECONDARY = "#f8f9fa"
COLOR_BG_TERTIARY = "#f1f3f5"
COLOR_TEXT_MAIN = "#212529"
COLOR_TEXT_SECONDARY = "#495057"
COLOR_TEXT_MUTED = "#868e96"
COLOR_BORDER = "#e9ecef"
COLOR_BORDER_FOCUS = "#74c0fc"
COLOR_SELECTION_BG = "#e7f5ff"
COLOR_SELECTION_TEXT = "#1971c2"
COLOR_CODE_TEXT = "#c2255c"

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

# ---------- 基础 QSS 片段 ----------
STYLESHEET_BUTTON_DEFAULT = f"""
    QPushButton {{
        background: {COLOR_BG_TERTIARY};
        color: {COLOR_TEXT_MAIN};
        border: 1px solid {COLOR_BORDER};
        border-radius: {RADIUS_DEFAULT};
        padding: {PADDING_DEFAULT};
        font-size: {FONT_SIZE_DEFAULT};
    }}
    QPushButton:hover {{
        background: {COLOR_BORDER};
        border-color: #dee2e6;
    }}
    QPushButton:pressed {{
        background: #dee2e6;
    }}
"""

STYLESHEET_BUTTON_PRIMARY = f"""
    QPushButton {{
        background: {COLOR_PRIMARY};
        color: white;
        border: none;
        border-radius: {RADIUS_LARGE};
        padding: {PADDING_DEFAULT};
        font-size: {FONT_SIZE_DEFAULT};
        font-weight: 500;
    }}
    QPushButton:hover {{ background: {COLOR_PRIMARY_HOVER}; }}
    QPushButton:pressed {{ background: {COLOR_PRIMARY_PRESSED}; }}
"""

STYLESHEET_BUTTON_DANGER = f"""
    QPushButton {{
        background: {COLOR_DANGER};
        color: white;
        border: none;
        border-radius: {RADIUS_LARGE};
        padding: {PADDING_DEFAULT};
        font-size: {FONT_SIZE_DEFAULT};
        font-weight: 500;
    }}
    QPushButton:hover {{ background: {COLOR_DANGER_HOVER}; }}
"""

STYLESHEET_INPUT = f"""
    QLineEdit {{
        background: {COLOR_BG_SECONDARY};
        color: {COLOR_TEXT_MAIN};
        border: 1px solid {COLOR_BORDER};
        border-radius: {RADIUS_LARGE};
        padding: {PADDING_DEFAULT};
        font-size: {FONT_SIZE_DEFAULT};
    }}
    QLineEdit:focus {{
        border-color: {COLOR_BORDER_FOCUS};
        background: {COLOR_BG_MAIN};
    }}
"""

STYLESHEET_LABEL_HEADER = f"""
    QLabel {{
        color: {COLOR_TEXT_MAIN};
        font-weight: 600;
        font-size: {FONT_SIZE_MEDIUM};
    }}
"""

STYLESHEET_LABEL_BODY = f"""
    QLabel {{
        color: {COLOR_TEXT_MAIN};
        font-size: {FONT_SIZE_DEFAULT};
    }}
"""

STYLESHEET_LABEL_CAPTION = f"""
    QLabel {{
        color: {COLOR_TEXT_MUTED};
        font-size: {FONT_SIZE_SMALL};
    }}
"""

STYLESHEET_TABLE = f"""
    QTableWidget {{
        background: {COLOR_BG_MAIN};
        color: {COLOR_TEXT_MAIN};
        gridline-color: {COLOR_BORDER};
        border: 1px solid {COLOR_BORDER};
        border-radius: {RADIUS_LARGE};
        outline: none;
    }}
    QHeaderView::section {{
        background: {COLOR_BG_SECONDARY};
        color: {COLOR_TEXT_SECONDARY};
        padding: 8px 12px;
        border: 1px solid {COLOR_BORDER};
        font-weight: 600;
    }}
    QTableWidget::item {{
        padding: 6px 10px;
    }}
    QTableWidget::item:selected {{
        background: {COLOR_SELECTION_BG};
        color: {COLOR_SELECTION_TEXT};
    }}
    QTableWidget::item:hover {{
        background: {COLOR_BG_SECONDARY};
    }}
"""

STYLESHEET_TREE = f"""
    QTreeWidget {{
        border: none;
        background: {COLOR_BG_MAIN};
        color: {COLOR_TEXT_MAIN};
        outline: none;
    }}
    QTreeWidget::item {{
        padding: 4px 2px;
        border-radius: {RADIUS_SMALL};
    }}
    QTreeWidget::item:selected {{
        background: {COLOR_SELECTION_BG};
        color: {COLOR_SELECTION_TEXT};
    }}
    QTreeWidget::item:hover {{
        background: {COLOR_BG_TERTIARY};
    }}
"""

STYLESHEET_CARD = f"""
    QFrame {{
        background: {COLOR_BG_MAIN};
        border: 1px solid {COLOR_BORDER};
        border-radius: {RADIUS_LARGE};
    }}
"""

STYLESHEET_DIALOG = f"""
    QDialog {{
        background: {COLOR_BG_MAIN};
    }}
    QLabel {{
        color: {COLOR_TEXT_MAIN};
    }}
    QLineEdit {{
        background: {COLOR_BG_SECONDARY};
        color: {COLOR_TEXT_MAIN};
        border: 1px solid {COLOR_BORDER};
        border-radius: {RADIUS_DEFAULT};
        padding: {PADDING_DEFAULT};
    }}
    QLineEdit:focus {{
        border-color: {COLOR_BORDER_FOCUS};
    }}
    QTextEdit {{
        background: {COLOR_BG_SECONDARY};
        color: {COLOR_TEXT_MAIN};
        border: 1px solid {COLOR_BORDER};
        border-radius: {RADIUS_DEFAULT};
        padding: {PADDING_DEFAULT};
    }}
    QComboBox {{
        background: {COLOR_BG_SECONDARY};
        color: {COLOR_TEXT_MAIN};
        border: 1px solid {COLOR_BORDER};
        border-radius: {RADIUS_DEFAULT};
        padding: {PADDING_DEFAULT};
    }}
    QSpinBox, QDoubleSpinBox {{
        background: {COLOR_BG_SECONDARY};
        color: {COLOR_TEXT_MAIN};
        border: 1px solid {COLOR_BORDER};
        border-radius: {RADIUS_DEFAULT};
        padding: {PADDING_DEFAULT};
    }}
    QPushButton {{
        background: {COLOR_BG_TERTIARY};
        color: {COLOR_TEXT_MAIN};
        border: 1px solid {COLOR_BORDER};
        border-radius: {RADIUS_DEFAULT};
        padding: {PADDING_DEFAULT};
    }}
    QPushButton:hover {{
        background: {COLOR_BORDER};
    }}
"""

STYLESHEET_TAB_WIDGET = f"""
    QTabWidget::pane {{
        border: 1px solid {COLOR_BORDER};
        border-radius: {RADIUS_LARGE};
        background: {COLOR_BG_MAIN};
    }}
    QTabBar::tab {{
        background: {COLOR_BG_TERTIARY};
        color: {COLOR_TEXT_MUTED};
        padding: 8px 18px;
        border: none;
        border-radius: {RADIUS_DEFAULT} {RADIUS_DEFAULT} 0 0;
        margin-right: 4px;
    }}
    QTabBar::tab:selected {{
        background: {COLOR_BG_MAIN};
        color: {COLOR_TEXT_MAIN};
        border: 1px solid {COLOR_BORDER};
        border-bottom: none;
    }}
    QTabBar::tab:hover {{
        background: {COLOR_BORDER};
        color: {COLOR_TEXT_SECONDARY};
    }}
"""


# ---------- 全局主题 QSS ----------
_GLOBAL_STYLESHEET = f"""
    /* ===== 全局 ===== */
    QMainWindow {{
        background: {COLOR_BG_MAIN};
    }}
    QWidget {{
        background: {COLOR_BG_MAIN};
        color: {COLOR_TEXT_MAIN};
    }}

    /* ===== 菜单栏 ===== */
    QMenuBar {{
        background: {COLOR_BG_SECONDARY};
        color: {COLOR_TEXT_MAIN};
        border-bottom: 1px solid {COLOR_BORDER};
        padding: 2px 6px;
    }}
    QMenuBar::item {{
        padding: 6px 14px;
        border-radius: {RADIUS_SMALL};
    }}
    QMenuBar::item:selected {{
        background: {COLOR_SELECTION_BG};
        color: {COLOR_SELECTION_TEXT};
    }}
    QMenu {{
        background: {COLOR_BG_MAIN};
        color: {COLOR_TEXT_MAIN};
        border: 1px solid {COLOR_BORDER};
        border-radius: {RADIUS_DEFAULT};
        padding: 6px;
    }}
    QMenu::item {{
        padding: 6px 20px;
        border-radius: {RADIUS_SMALL};
    }}
    QMenu::item:selected {{
        background: {COLOR_SELECTION_BG};
        color: {COLOR_SELECTION_TEXT};
    }}
    QMenu::separator {{
        height: 1px;
        background: {COLOR_BORDER};
        margin: 6px 12px;
    }}

    /* ===== 工具栏 ===== */
    QToolBar {{
        background: {COLOR_BG_SECONDARY};
        border: none;
        border-bottom: 1px solid {COLOR_BORDER};
        spacing: 6px;
        padding: 6px 10px;
    }}
    QToolButton {{
        background: transparent;
        color: {COLOR_TEXT_SECONDARY};
        border: none;
        border-radius: {RADIUS_DEFAULT};
        padding: 6px 14px;
        font-size: {FONT_SIZE_DEFAULT};
    }}
    QToolButton:hover {{
        background: {COLOR_BORDER};
        color: {COLOR_TEXT_MAIN};
    }}

    /* ===== 状态栏 ===== */
    QStatusBar {{
        background: {COLOR_BG_SECONDARY};
        color: {COLOR_TEXT_SECONDARY};
        border-top: 1px solid {COLOR_BORDER};
        padding: 2px 12px;
    }}

    /* ===== 标签页 ===== */
    {STYLESHEET_TAB_WIDGET}

    /* ===== 按钮 ===== */
    {STYLESHEET_BUTTON_DEFAULT}

    /* ===== 输入框 ===== */
    {STYLESHEET_INPUT}

    /* ===== 分割器 ===== */
    QSplitter::handle {{
        background: {COLOR_BORDER};
    }}
    QSplitter::handle:horizontal {{
        width: 2px;
    }}

    /* ===== 标签 ===== */
    QLabel {{
        color: {COLOR_TEXT_MAIN};
    }}
"""


class ThemeManager:
    """全局主题管理器，提供统一的样式应用接口."""

    @staticmethod
    def global_stylesheet() -> str:
        """返回全局 QSS 字符串."""
        return _GLOBAL_STYLESHEET

    @staticmethod
    def apply_global(widget: QWidget) -> None:
        """对指定 widget 应用全局样式（通常用于 QMainWindow）."""
        widget.setStyleSheet(_GLOBAL_STYLESHEET)

    @staticmethod
    def apply_dialog(dialog: QWidget) -> None:
        """对对话框应用统一样式."""
        dialog.setStyleSheet(STYLESHEET_DIALOG)


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
    if style == "primary":
        btn.setStyleSheet(STYLESHEET_BUTTON_PRIMARY)
    elif style == "danger":
        btn.setStyleSheet(STYLESHEET_BUTTON_DANGER)
    else:
        btn.setStyleSheet(STYLESHEET_BUTTON_DEFAULT)
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
    edit = QLineEdit(parent)
    edit.setPlaceholderText(placeholder)
    edit.setStyleSheet(STYLESHEET_INPUT)
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
    label = QLabel(text, parent)
    if level == "header":
        label.setStyleSheet(STYLESHEET_LABEL_HEADER)
    elif level == "caption":
        label.setStyleSheet(STYLESHEET_LABEL_CAPTION)
    else:
        label.setStyleSheet(STYLESHEET_LABEL_BODY)
    return label


def create_table(headers: list[str], parent: Optional[QWidget] = None) -> QTableWidget:
    """创建统一风格的表格.

    Args:
        headers: 表头列表
        parent: 父 widget
    """
    table = QTableWidget(parent)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setStyleSheet(STYLESHEET_TABLE)
    return table


def create_tree(parent: Optional[QWidget] = None) -> QTreeWidget:
    """创建统一风格的树形组件."""
    tree = QTreeWidget(parent)
    tree.setStyleSheet(STYLESHEET_TREE)
    return tree


class CardWidget(QFrame):
    """卡片容器组件，带圆角边框和标题."""

    def __init__(
        self,
        title: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setStyleSheet(STYLESHEET_CARD)
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
        self.setPlaceholderText(f"🔍 {placeholder}")
        self.setStyleSheet(f"""
            QLineEdit {{
                background: {COLOR_BG_SECONDARY};
                color: {COLOR_TEXT_MAIN};
                border: 1px solid {COLOR_BORDER};
                border-radius: {RADIUS_LARGE};
                padding: 6px 12px 6px 32px;
                font-size: {FONT_SIZE_DEFAULT};
            }}
            QLineEdit:focus {{
                border-color: {COLOR_BORDER_FOCUS};
                background: {COLOR_BG_MAIN};
            }}
        """)
        self.setMinimumHeight(32)
