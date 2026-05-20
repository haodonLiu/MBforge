"""PDF 查看器."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class PDFViewer(QWidget):
    """基于 PyMuPDF 的 PDF 查看器（渲染为图片）."""

    page_changed = pyqtSignal(int, int)  # current, total

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.doc: Optional[fitz.Document] = None
        self.current_page = 0
        self._scale = 1.5

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setStyleSheet("background: #1e1e1e; border: none;")

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("background: #1e1e1e;")
        self.scroll.setWidget(self.label)
        layout.addWidget(self.scroll)

    def load_pdf(self, path: Path):
        if self.doc:
            self.doc.close()
            self.doc = None
        try:
            self.doc = fitz.open(str(path))
            self.current_page = 0
            self._render_page()
        except Exception as e:
            self.label.setText(f"无法加载 PDF: {e}")

    def _render_page(self):
        if self.doc is None or self.current_page >= len(self.doc):
            return
        try:
            page = self.doc[self.current_page]
            mat = fitz.Matrix(self._scale, self._scale)
            pix = page.get_pixmap(matrix=mat)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            self.label.setPixmap(QPixmap.fromImage(img))
            self.label.setFixedSize(pix.width, pix.height)
            self.page_changed.emit(self.current_page + 1, len(self.doc))
        except Exception as e:
            self.label.setText(f"渲染页面失败: {e}")

    def next_page(self):
        if self.doc and self.current_page < len(self.doc) - 1:
            self.current_page += 1
            self._render_page()

    def prev_page(self):
        if self.doc and self.current_page > 0:
            self.current_page -= 1
            self._render_page()

    def zoom_in(self):
        self._scale *= 1.2
        self._render_page()

    def zoom_out(self):
        self._scale /= 1.2
        self._render_page()

    def close_document(self):
        if self.doc:
            self.doc.close()
            self.doc = None
        self.label.clear()
