"""支持划词选区的PDF页面标签."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QRect
from PyQt6.QtGui import QPainter, QPen, QColor
from PyQt6.QtWidgets import QLabel, QMenu, QWidget


class PDFPageLabel(QLabel):
    """支持鼠标拖拽划词选区的PDF页面标签."""

    highlight_requested = pyqtSignal(int, QRect)
    clear_highlights_requested = pyqtSignal(int)
    copy_text_requested = pyqtSignal(int, QRect)
    molecule_extract_requested = pyqtSignal(int, QRect)

    def __init__(self, page_index: int, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.page_index = page_index
        self.setMouseTracking(True)
        self._selecting = False
        self._start_pos = None
        self._end_pos = None
        self._selection_rect = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._selecting = True
            self._start_pos = event.pos()
            self._end_pos = event.pos()
            self._selection_rect = None
            self.update()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._selecting:
            self._end_pos = event.pos()
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._selecting and event.button() == Qt.MouseButton.LeftButton:
            self._selecting = False
            self._end_pos = event.pos()
            rect = self._make_rect()
            if rect and rect.width() > 3 and rect.height() > 3:
                self._selection_rect = rect
                self.highlight_requested.emit(self.page_index, rect)
            else:
                self._selection_rect = None
            self.update()
            event.accept()

    def paintEvent(self, event):
        super().paintEvent(event)
        rect = self._make_rect() if self._selecting else self._selection_rect
        if rect:
            painter = QPainter(self)
            painter.setPen(QPen(QColor(0, 120, 215), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(0, 120, 215, 40))
            painter.drawRect(rect)
            painter.end()

    def _make_rect(self):
        if self._start_pos and self._end_pos:
            x1 = min(self._start_pos.x(), self._end_pos.x())
            y1 = min(self._start_pos.y(), self._end_pos.y())
            x2 = max(self._start_pos.x(), self._end_pos.x())
            y2 = max(self._start_pos.y(), self._end_pos.y())
            return QRect(x1, y1, x2 - x1, y2 - y1)
        return None

    def clear_selection(self):
        self._selecting = False
        self._selection_rect = None
        self.update()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        if self._selection_rect:
            copy_action = menu.addAction("复制选中文本")
            copy_action.triggered.connect(
                lambda: self.copy_text_requested.emit(self.page_index, self._selection_rect)
            )
            menu.addSeparator()
            extract_action = menu.addAction("识别选中区域分子")
            extract_action.triggered.connect(
                lambda: self.molecule_extract_requested.emit(self.page_index, self._selection_rect)
            )
        clear_action = menu.addAction("清除本页高亮")
        clear_action.triggered.connect(
            lambda: self.clear_highlights_requested.emit(self.page_index)
        )
        menu.exec(event.globalPos())
