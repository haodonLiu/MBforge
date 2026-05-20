"""PDF 查看器."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import fitz  # PyMuPDF
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class PDFViewer(QWidget):
    """基于 PyMuPDF 的 PDF 查看器（支持单页/连续翻页）."""

    page_changed = pyqtSignal(int, int)  # current, total

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.doc: Optional[fitz.Document] = None
        self.current_page = 0
        self._scale = 1.5
        self._continuous_mode = True
        self._page_labels: List[QLabel] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ---- 工具栏 ----
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 4, 8, 4)

        self.btn_mode = QPushButton("📜 连续")
        self.btn_mode.setToolTip("切换单页/连续模式")
        self.btn_mode.clicked.connect(self._toggle_mode)
        toolbar.addWidget(self.btn_mode)

        toolbar.addSpacing(12)

        self.btn_prev = QPushButton("◀ 上一页")
        self.btn_prev.setEnabled(False)
        self.btn_prev.clicked.connect(self.prev_page)
        toolbar.addWidget(self.btn_prev)

        toolbar.addStretch()

        self.page_label = QLabel("0 / 0")
        self.page_label.setStyleSheet("font-size: 13px; color: #495057;")
        toolbar.addWidget(self.page_label)

        self.page_input = QSpinBox()
        self.page_input.setMinimum(1)
        self.page_input.setMaximum(1)
        self.page_input.setFixedWidth(60)
        self.page_input.setStyleSheet("font-size: 13px;")
        self.page_input.editingFinished.connect(self._jump_to_page_input)
        toolbar.addWidget(self.page_input)

        toolbar.addStretch()

        self.btn_next = QPushButton("下一页 ▶")
        self.btn_next.setEnabled(False)
        self.btn_next.clicked.connect(self.next_page)
        toolbar.addWidget(self.btn_next)

        toolbar.addSpacing(16)

        btn_zoom_out = QPushButton("🔍-")
        btn_zoom_out.setToolTip("缩小")
        btn_zoom_out.clicked.connect(self.zoom_out)
        toolbar.addWidget(btn_zoom_out)

        btn_zoom_in = QPushButton("🔍+")
        btn_zoom_in.setToolTip("放大")
        btn_zoom_in.clicked.connect(self.zoom_in)
        toolbar.addWidget(btn_zoom_in)

        layout.addLayout(toolbar)

        # ---- 滚动区域 ----
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setStyleSheet("background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 10px;")

        # 单页标签
        self.single_label = QLabel()
        self.single_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.single_label.setStyleSheet("background: #f8f9fa; border-radius: 10px;")

        # 连续模式容器
        self.continuous_widget = QWidget()
        self.continuous_layout = QVBoxLayout(self.continuous_widget)
        self.continuous_layout.setSpacing(12)
        self.continuous_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.continuous_layout.setContentsMargins(12, 12, 12, 12)

        self.scroll.setWidget(self.continuous_widget)
        layout.addWidget(self.scroll, 1)

    def _toggle_mode(self):
        self._continuous_mode = not self._continuous_mode
        self.btn_mode.setText("📜 连续" if self._continuous_mode else "📄 单页")
        self._render()

    def load_pdf(self, path: Path):
        if self.doc:
            self.doc.close()
            self.doc = None
        try:
            self.doc = fitz.open(str(path))
            self.current_page = 0
            self._render()
        except Exception as e:
            self._clear_pages()
            self.single_label.setText(f"无法加载 PDF: {e}")

    def _render(self):
        if self.doc is None:
            return
        if self._continuous_mode:
            self._render_continuous()
        else:
            self._render_single()
        self._update_toolbar()

    def _render_single(self):
        """渲染单页模式."""
        self._clear_pages()
        self.scroll.setWidget(self.single_label)
        page = self.doc[self.current_page]
        mat = fitz.Matrix(self._scale, self._scale)
        pix = page.get_pixmap(matrix=mat)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
        self.single_label.setPixmap(QPixmap.fromImage(img))
        self.single_label.setFixedSize(pix.width, pix.height)
        self.page_changed.emit(self.current_page + 1, len(self.doc))

    def _render_continuous(self):
        """渲染连续翻页模式."""
        self._clear_pages()
        # QScrollArea.setWidget 会接管旧 widget 的所有权并可能删除它，
        # 所以每次切换都重建 continuous_widget
        self.continuous_widget = QWidget()
        self.continuous_layout = QVBoxLayout(self.continuous_widget)
        self.continuous_layout.setSpacing(12)
        self.continuous_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.continuous_layout.setContentsMargins(12, 12, 12, 12)
        self.scroll.setWidget(self.continuous_widget)

        for i in range(len(self.doc)):
            page = self.doc[i]
            mat = fitz.Matrix(self._scale, self._scale)
            pix = page.get_pixmap(matrix=mat)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)

            label = QLabel()
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setPixmap(QPixmap.fromImage(img))
            label.setFixedSize(pix.width, pix.height)
            label.setStyleSheet("background: #ffffff; border: 1px solid #e9ecef; border-radius: 4px;")

            # 页码标签
            page_num = QLabel(f"— 第 {i + 1} 页 —")
            page_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            page_num.setStyleSheet("color: #adb5bd; font-size: 12px; padding: 4px;")

            self.continuous_layout.addWidget(page_num)
            self.continuous_layout.addWidget(label)
            self._page_labels.append(label)
            self._page_labels.append(page_num)

        self.continuous_layout.addStretch()
        self.page_changed.emit(self.current_page + 1, len(self.doc))

    def _clear_pages(self):
        """清空连续模式下的所有页面."""
        self.single_label.clear()
        self.single_label.setFixedSize(0, 0)
        for label in self._page_labels:
            label.deleteLater()
        self._page_labels.clear()

    def _update_toolbar(self):
        total = len(self.doc) if self.doc else 0
        current = self.current_page + 1 if self.doc else 0

        # 连续模式下禁用单页翻页按钮（通过滚动浏览）
        self.btn_prev.setEnabled(
            self.doc is not None
            and self.current_page > 0
            and not self._continuous_mode
        )
        self.btn_next.setEnabled(
            self.doc is not None
            and self.current_page < total - 1
            and not self._continuous_mode
        )
        self.page_label.setText(f"第 {current} / {total} 页")
        self.page_input.setMaximum(total)
        self.page_input.setValue(current)

    def _jump_to_page_input(self):
        if self.doc is None:
            return
        page = self.page_input.value() - 1
        if 0 <= page < len(self.doc):
            self.current_page = page
            if self._continuous_mode:
                # 滚动到对应页面
                if page < len(self._page_labels) // 2:
                    target = self._page_labels[page * 2]
                    self.scroll.ensureWidgetVisible(target, 50, 50)
            else:
                self._render_single()
            self._update_toolbar()

    def next_page(self):
        if self.doc and self.current_page < len(self.doc) - 1:
            self.current_page += 1
            self._render_single()

    def prev_page(self):
        if self.doc and self.current_page > 0:
            self.current_page -= 1
            self._render_single()

    def zoom_in(self):
        self._scale *= 1.2
        self._render()

    def zoom_out(self):
        self._scale /= 1.2
        self._render()

    def close_document(self):
        if self.doc:
            self.doc.close()
            self.doc = None
        self._clear_pages()
        self._update_toolbar()
