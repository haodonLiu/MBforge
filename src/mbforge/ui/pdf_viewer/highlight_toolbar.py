"""PDF 高亮工具栏 — 颜色与样式切换."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QButtonGroup, QLabel


class HighlightToolbar(QWidget):
    """PDF 高亮工具栏：颜色 + 样式切换."""

    color_changed = pyqtSignal(tuple)  # (r, g, b) 0.0-1.0
    style_changed = pyqtSignal(str)  # "background" | "underline"

    PRESETS: list[tuple[str, tuple[float, float, float]]] = [
        ("黄色", (1.0, 1.0, 0.0)),
        ("绿色", (0.0, 1.0, 0.0)),
        ("蓝色", (0.0, 0.5, 1.0)),
        ("粉色", (1.0, 0.5, 0.8)),
        ("橙色", (1.0, 0.6, 0.0)),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        layout.addWidget(QLabel("高亮颜色:"))
        self._color_group = QButtonGroup(self)
        for name, rgb in self.PRESETS:
            btn = QPushButton(name)
            r, g, b = rgb
            btn.setStyleSheet(
                f"background-color: rgb({int(r * 255)},{int(g * 255)},{int(b * 255)});"
                f"border: 1px solid gray; padding: 2px 8px;"
            )
            btn.setCheckable(True)
            self._color_group.addButton(btn)
            layout.addWidget(btn)
            btn.toggled.connect(
                lambda checked, c=rgb: checked and self.color_changed.emit(c)
            )

        first_btn = self._color_group.buttons()[0]
        if first_btn:
            first_btn.setChecked(True)

        layout.addSpacing(16)
        layout.addWidget(QLabel("样式:"))
        self._btn_bg = QPushButton("背景")
        self._btn_underline = QPushButton("下划线")
        self._btn_bg.setCheckable(True)
        self._btn_underline.setCheckable(True)
        self._btn_bg.setChecked(True)
        layout.addWidget(self._btn_bg)
        layout.addWidget(self._btn_underline)

        self._btn_bg.toggled.connect(
            lambda c: c and self.style_changed.emit("background")
        )
        self._btn_underline.toggled.connect(
            lambda c: c and self.style_changed.emit("underline")
        )

    def current_color(self) -> tuple[float, float, float]:
        """返回当前选中的颜色."""
        checked = self._color_group.checkedButton()
        if checked:
            idx = self._color_group.buttons().index(checked)
            return self.PRESETS[idx][1]
        return (1.0, 1.0, 0.0)

    def current_style(self) -> str:
        """返回当前选中的样式."""
        if self._btn_underline.isChecked():
            return "underline"
        return "background"
