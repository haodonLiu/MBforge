"""支持划词选区的PDF页面标签."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import QPainter, QPen, QColor
from PyQt6.QtWidgets import QLabel, QMenu, QWidget


class PDFPageLabel(QLabel):
    """支持鼠标拖拽划词选区的PDF页面标签."""

    highlight_requested = pyqtSignal(int, QRect)
    clear_highlights_requested = pyqtSignal(int)
    copy_text_requested = pyqtSignal(int, QRect)
    molecule_extract_requested = pyqtSignal(int, QRect)

    # 新增信号
    detection_clicked = pyqtSignal(int, str)  # page_index, detection_id
    detection_ctrl_clicked = pyqtSignal(int, str, QPoint)  # page_index, det_id, pos
    highlight_double_clicked = pyqtSignal(int, str)  # page_index, highlight_id

    def __init__(self, page_index: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.page_index = page_index
        self.setMouseTracking(True)
        self._selecting = False
        self._start_pos = None
        self._end_pos = None
        self._selection_rect = None

        # 用于命中测试的 detection 屏幕坐标映射
        self._detection_rects: dict[str, QRect] = {}
        # 用于命中测试的 highlight 屏幕坐标映射
        self._highlight_rects: dict[str, QRect] = {}

        # Ctrl+拖拽调整大小状态
        self._resizing_detection_id: str | None = None
        self._resize_start_pos: QPoint | None = None
        self._resize_current_pos: QPoint | None = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 先检测是否命中 detection box
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                det_id = self._hit_test_detection(event.pos())
                if det_id:
                    self._resizing_detection_id = det_id
                    self._resize_start_pos = event.pos()
                    self.detection_ctrl_clicked.emit(
                        self.page_index, det_id, event.pos()
                    )
                    event.accept()
                    return
            else:
                det_id = self._hit_test_detection(event.pos())
                if det_id:
                    self.detection_clicked.emit(self.page_index, det_id)
                    event.accept()
                    return

                hl_id = self._hit_test_highlight(event.pos())
                if hl_id:
                    # 单击高亮不处理，留给双击
                    pass

            # 否则进入原有划词模式
            self._selecting = True
            self._start_pos = event.pos()
            self._end_pos = event.pos()
            self._selection_rect = None
            self.update()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._resizing_detection_id and self._resize_start_pos:
            self._resize_current_pos = event.pos()
            self.update()
            event.accept()
            return
        if self._selecting:
            self._end_pos = event.pos()
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._resizing_detection_id and event.button() == Qt.MouseButton.LeftButton:
            self.detection_ctrl_clicked.emit(
                self.page_index, self._resizing_detection_id, event.pos()
            )
            self._resizing_detection_id = None
            self._resize_start_pos = None
            self._resize_current_pos = None
            event.accept()
            return

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

    def mouseDoubleClickEvent(self, event):
        hl_id = self._hit_test_highlight(event.pos())
        if hl_id:
            self.highlight_double_clicked.emit(self.page_index, hl_id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        rect = self._make_rect() if self._selecting else self._selection_rect
        if rect:
            painter = QPainter(self)
            painter.setPen(QPen(QColor(0, 120, 215), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(0, 120, 215, 40))
            painter.drawRect(rect)
            painter.end()

        # 绘制 resize 中的虚线框
        if self._resizing_detection_id and self._resize_current_pos:
            painter = QPainter(self)
            painter.setPen(QPen(QColor(255, 0, 0), 1, Qt.PenStyle.DashLine))
            orig = self._detection_rects.get(self._resizing_detection_id)
            if orig:
                new_rect = QRect(orig.topLeft(), self._resize_current_pos).normalized()
                painter.drawRect(new_rect)
            painter.end()

    def _make_rect(self):
        if self._start_pos and self._end_pos:
            x1 = min(self._start_pos.x(), self._end_pos.x())
            y1 = min(self._start_pos.y(), self._end_pos.y())
            x2 = max(self._start_pos.x(), self._end_pos.x())
            y2 = max(self._start_pos.y(), self._end_pos.y())
            return QRect(x1, y1, x2 - x1, y2 - y1)
        return None

    def _hit_test_detection(self, pos: QPoint) -> str | None:
        for det_id, bbox in self._detection_rects.items():
            if bbox.contains(pos):
                return det_id
        return None

    def _hit_test_highlight(self, pos: QPoint) -> str | None:
        for hl_id, bbox in self._highlight_rects.items():
            if bbox.contains(pos):
                return hl_id
        return None

    def clear_selection(self):
        self._selecting = False
        self._selection_rect = None
        self._resizing_detection_id = None
        self._resize_start_pos = None
        self._resize_current_pos = None
        self.update()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        if self._selection_rect:
            copy_action = menu.addAction("复制选中文本")
            copy_action.triggered.connect(
                lambda: self.copy_text_requested.emit(
                    self.page_index, self._selection_rect
                )
            )
            menu.addSeparator()
            extract_action = menu.addAction("识别选中区域分子")
            extract_action.triggered.connect(
                lambda: self.molecule_extract_requested.emit(
                    self.page_index, self._selection_rect
                )
            )
        clear_action = menu.addAction("清除本页高亮")
        clear_action.triggered.connect(
            lambda: self.clear_highlights_requested.emit(self.page_index)
        )
        menu.exec(event.globalPos())
