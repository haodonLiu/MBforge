"""PDF 查看器 — 支持大文档虚拟滚动连续加载."""

from __future__ import annotations

import atexit
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional

import fitz  # PyMuPDF
from PyQt6.QtCore import QEvent, QTimer, pyqtSignal, pyqtSlot, Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


# 全局线程池，最多 4 个 worker（防止大文档渲染时过度抢占 CPU）
_NWORKERS = min(4, max(1, __import__("os").cpu_count() or 4))
_executor: ThreadPoolExecutor = ThreadPoolExecutor(
    max_workers=_NWORKERS, thread_name_prefix="pdf_render"
)
atexit.register(lambda: _executor.shutdown(wait=True))


def _render_page_range(path: str, scale: float, indices: List[int]) -> List[tuple]:
    """在线程池worker中渲染一组页，返回 (index, QImage) 列表。

    每个 worker 独立打开 fitz.Document，避免跨线程共享 fitz 对象。
    QImage 被文档声明为可重入，可安全跨线程传递。
    """
    results = []
    doc = fitz.open(path)
    try:
        for idx in indices:
            page = doc[idx]
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat)
            img = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            )
            results.append((idx, img))
    finally:
        doc.close()
    return results


class PDFViewer(QWidget):
    """基于 PyMuPDF 的 PDF 查看器（虚拟滚动连续模式）."""

    page_changed = pyqtSignal(int, int)  # current, total
    _pages_done = pyqtSignal(list)  # 内部信号，在主线程触发 _on_pages_ready

    # 虚拟滚动缓冲：视口上下各额外渲染 N 页
    BUFFER_PAGES = 5

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.doc: Optional[fitz.Document] = None
        self._doc_path: Optional[str] = None
        self.current_page = 0
        self._scale = 1.5

        # 虚拟滚动状态
        self._continuous_mode = True
        self._virtual_container: Optional[QWidget] = None
        self._page_heights: List[int] = []  # 每页渲染高度（pt * scale）
        self._page_widths: List[int] = []  # 每页渲染宽度
        self._page_cache: Dict[int, QPixmap] = {}  # index -> rendered pixmap
        self._visible_widgets: Dict[
            int, QWidget
        ] = {}  # 当前显示的 index -> (num_label, img_label)
        self._pending_indices: set = set()  # 正在后台渲染的索引
        self._all_indices_rendered: bool = False  # 是否全部渲染完成

        # 后台线程
        self._rendered_count = 0
        self._total_pages = 0

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

        self.progress = QProgressBar()
        self.progress.setFixedWidth(120)
        self.progress.setVisible(False)
        self.progress.setStyleSheet("QProgressBar { border: none; }")
        toolbar.addWidget(self.progress)

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
        self.scroll.setStyleSheet(
            "background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 10px;"
        )
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.scroll.viewport().installEventFilter(self)  # 监听 viewport resize

        # 单页模式
        self.single_label: Optional[QLabel] = None

        self.scroll.setWidget(self.single_label)
        layout.addWidget(self.scroll, 1)

        # 多线程渲染信号连接
        self._pages_done.connect(
            self._on_pages_ready, Qt.ConnectionType.QueuedConnection
        )

        self._page_height_approx = 800  # 估算页高，后续精确

    def _stop_background(self):
        """通过清空 pending 集合取消在途渲染任务（结果会被丢弃）。"""
        self._pending_indices.clear()

    def _toggle_mode(self):
        self._continuous_mode = not self._continuous_mode
        self.btn_mode.setText("📜 连续" if self._continuous_mode else "📄 单页")
        self._render()

    def load_pdf(self, path: Path):
        self._stop_background()
        if self.doc:
            self.doc.close()
            self.doc = None
        try:
            self.doc = fitz.open(str(path))
            self._doc_path = str(path.resolve())
            self._total_pages = len(self.doc)
            self.current_page = 0
            self._page_cache.clear()
            self._visible_widgets.clear()
            self._pending_indices.clear()
            self._all_indices_rendered = False
            self._rendered_count = 0
            self._precompute_page_sizes()
            self._render()
        except Exception as e:
            self._clear_visible_widgets()
            self.single_label = QLabel()
            self.single_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.single_label.setStyleSheet("background: #f8f9fa; border-radius: 10px;")
            self.single_label.setText(f"无法加载 PDF: {e}")
            self.scroll.setWidget(self.single_label)

    def _precompute_page_sizes(self):
        """预先计算每页渲染尺寸（只取 mediabox，不实际渲染）。"""
        self._page_heights = []
        self._page_widths = []
        for i in range(len(self.doc)):
            rect = self.doc[i].mediabox
            w = int(rect.width * self._scale)
            h = int(rect.height * self._scale)
            self._page_heights.append(h + 30)  # 页码标签高度
            self._page_widths.append(w)

    def _total_height(self) -> int:
        return sum(self._page_heights)

    def _render(self):
        if self.doc is None:
            return
        self._stop_background()
        self._clear_visible_widgets()
        if self._continuous_mode:
            self._render_continuous_virtual()
        else:
            self._render_single()
        self._update_toolbar()

    def _render_continuous_virtual(self):
        """虚拟滚动连续模式：建立容器，渲染首屏。"""
        self._clear_visible_widgets()

        # 建立虚拟容器（只决定滚动条范围，不承载实际子 widget）
        self._virtual_container = QWidget()
        self._virtual_container.setMinimumSize(
            max(self._page_widths), self._total_height()
        )
        self._virtual_container.setMaximumSize(
            max(self._page_widths), self._total_height()
        )
        self._virtual_container.setLayout(QVBoxLayout())
        self._virtual_container.layout().setSpacing(0)
        self._virtual_container.layout().setContentsMargins(0, 0, 0, 0)
        self.scroll.setWidget(self._virtual_container)
        self.scroll.verticalScrollBar().setValue(0)

        # 渲染首屏可见页（同步）
        self._render_visible_range()
        self.page_changed.emit(self.current_page + 1, self._total_pages)
        # 布局完成后重新渲染：首次加载时 viewport 高度可能为 0
        QTimer.singleShot(0, self._rerender_if_needed)

    def _render_visible_range(self):
        """根据当前滚动位置，渲染可见页范围内所有页，回收范围外页。"""
        if not self._virtual_container:
            return

        vp = self.scroll.viewport()
        scroll_y = self.scroll.verticalScrollBar().value()
        vis_top = scroll_y
        vis_bottom = scroll_y + vp.height()

        # 计算可见页索引范围
        cum = 0
        start_idx = 0
        end_idx = self._total_pages - 1
        for i, h in enumerate(self._page_heights):
            page_top = cum
            page_bottom = cum + h
            if page_bottom >= vis_top and start_idx == 0:
                start_idx = max(0, i - self.BUFFER_PAGES)
            if page_top <= vis_bottom:
                end_idx = min(self._total_pages - 1, i + self.BUFFER_PAGES)
            cum += h

        # 回收已移出范围的页
        to_remove = [
            idx
            for idx in list(self._visible_widgets)
            if idx < start_idx or idx > end_idx
        ]
        for idx in to_remove:
            w_num, w_img = self._visible_widgets.pop(idx)
            w_num.deleteLater()
            w_img.deleteLater()

        # 渲染范围内缺失的页
        to_render: List[int] = []
        for i in range(start_idx, end_idx + 1):
            if i not in self._visible_widgets and i not in self._pending_indices:
                if i in self._page_cache:
                    self._place_page_widget(i, self._page_cache[i])
                else:
                    to_render.append(i)

        if to_render:
            # 批量同步渲染（Qt 不允许跨线程操作 UI，先在主线程渲染）
            for idx in to_render:
                self._render_page_sync(idx)

        # 补齐还未渲染的页面（触发后台）
        still_missing = [idx for idx in to_render if idx not in self._page_cache]
        if still_missing and not self._all_indices_rendered:
            self._start_background_render(still_missing)

    def _render_page_sync(self, index: int) -> bool:
        """同步渲染单页，返回是否成功。"""
        if self.doc is None or index in self._page_cache:
            return False
        try:
            page = self.doc[index]
            mat = fitz.Matrix(self._scale, self._scale)
            pix = page.get_pixmap(matrix=mat)
            img = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            )
            pm = QPixmap.fromImage(img)
            self._page_cache[index] = pm
            self._place_page_widget(index, pm)
            self._rendered_count += 1
            return True
        except Exception:
            return False

    def _place_page_widget(self, index: int, pixmap: QPixmap):
        """将渲染好的 pixmap 放入虚拟容器的正确位置。"""
        if index in self._visible_widgets or not self._virtual_container:
            return

        num_label = QLabel(f"— 第 {index + 1} 页 —", self._virtual_container)
        num_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num_label.setStyleSheet("color: #adb5bd; font-size: 12px; padding: 4px;")
        num_label.move(0, self._page_offset(index))
        num_label.resize(max(self._page_widths), 25)
        num_label.show()

        img_label = QLabel(self._virtual_container)
        img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_label.setPixmap(pixmap)
        img_label.setFixedSize(pixmap.width(), pixmap.height())
        img_label.setStyleSheet(
            "background: #ffffff; border: 1px solid #e9ecef; border-radius: 4px;"
        )
        img_label.move(0, self._page_offset(index) + 25)
        img_label.resize(pixmap.width(), pixmap.height())
        img_label.show()

        self._visible_widgets[index] = (num_label, img_label)

    def _page_offset(self, index: int) -> int:
        """第 index 页相对于容器顶部的 Y 偏移。"""
        return sum(self._page_heights[:index])

    def _start_background_render(self, indices: List[int]):
        """使用线程池并行渲染指定页。"""
        if not indices:
            return
        self._pending_indices.update(indices)

        # 将页索引分片，每 worker 一组
        n = min(len(indices), _NWORKERS)
        chunk_size = max(1, len(indices) // n)
        chunks = [
            indices[i : i + chunk_size] for i in range(0, len(indices), chunk_size)
        ]

        self.progress.setMaximum(self._total_pages)
        self.progress.setVisible(True)

        for chunk in chunks:
            _executor.submit(
                _render_page_range,
                self._doc_path,
                self._scale,
                chunk,
            ).add_done_callback(self._on_future_done)

    def _on_future_done(self, future):
        """线程池 future 完成回调，通过信号切回主线程。"""
        try:
            results = future.result()
        except Exception:
            return
        # 主线程安全调度
        self._pages_done.emit(results)

    @pyqtSlot(list)
    def _on_pages_ready(self, batch: List):
        """主线程收到渲染好的页（QImage），转为 QPixmap 并放入缓存和 UI。"""
        if not batch:
            return
        for idx, qimage in batch:
            if idx in self._pending_indices:
                self._pending_indices.discard(idx)
            if idx not in self._page_cache:
                # QPixmap 必须在 GUI 线程创建
                self._page_cache[idx] = QPixmap.fromImage(qimage)
                self._rendered_count += 1
            else:
                # 缓存命中
                pass
            # 已在可见范围则直接放入 widget
            if self._virtual_container and (
                idx in self._visible_widgets or self._is_index_visible(idx)
            ):
                self._place_page_widget(idx, self._page_cache[idx])
        self.progress.setValue(self._rendered_count)
        if not self._pending_indices:
            self.progress.setVisible(False)
            self._all_indices_rendered = True

    def _is_index_visible(self, index: int) -> bool:
        if not self._virtual_container:
            return False
        vp = self.scroll.viewport()
        scroll_y = self.scroll.verticalScrollBar().value()
        vis_top = scroll_y
        vis_bottom = scroll_y + vp.height()
        off = self._page_offset(index)
        page_h = self._page_heights[index]
        return off < vis_bottom and off + page_h > vis_top

    def _on_scroll(self):
        """滚动时更新可见页。"""
        if self._continuous_mode and self._virtual_container:
            self._render_visible_range()

    def _on_viewport_resize(self):
        """窗口大小变化时重新计算可见范围。"""
        if self._continuous_mode and self._virtual_container:
            self._render_visible_range()

    def _rerender_if_needed(self):
        """布局完成后检查：若首屏未渲染则重新渲染。"""
        if (
            self._continuous_mode
            and self._virtual_container
            and not self._visible_widgets
        ):
            self._render_visible_range()

    def _render_single(self):
        """单页模式（按需渲染，无虚拟滚动开销）。"""
        self._clear_visible_widgets()
        # 每次重建 single_label，避免 Qt setWidget 替换后 C++ 对象已删除的问题
        self.single_label = QLabel()
        self.single_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.single_label.setStyleSheet("background: #f8f9fa; border-radius: 10px;")
        self.scroll.setWidget(self.single_label)
        self.single_label.clear()
        page = self.doc[self.current_page]
        mat = fitz.Matrix(self._scale, self._scale)
        pix = page.get_pixmap(matrix=mat)
        img = QImage(
            pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888
        )
        self.single_label.setPixmap(QPixmap.fromImage(img))
        self.single_label.setFixedSize(pix.width, pix.height)
        self.page_changed.emit(self.current_page + 1, self._total_pages)

    def _clear_visible_widgets(self):
        """清空虚拟滚动容器中的所有子 widget。"""
        for w_num, w_img in self._visible_widgets.values():
            w_num.deleteLater()
            w_img.deleteLater()
        self._visible_widgets.clear()
        if self._virtual_container:
            self._virtual_container.deleteLater()
            self._virtual_container = None

    def _scroll_to_current_page(self):
        """在连续模式下滚动到当前页。"""
        if self._virtual_container:
            target_y = self._page_offset(self.current_page)
            bar = self.scroll.verticalScrollBar()
            bar.setValue(target_y - self.scroll.viewport().height() // 2)

    def _update_toolbar(self):
        total = self._total_pages
        current = self.current_page + 1
        self.btn_prev.setEnabled(
            self.doc is not None and self.current_page > 0 and not self._continuous_mode
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
        if 0 <= page < self._total_pages:
            self.current_page = page
            if self._continuous_mode and self._virtual_container:
                target_y = self._page_offset(page)
                self.scroll.verticalScrollBar().setValue(target_y)
            else:
                self._render_single()
            self._update_toolbar()

    def next_page(self):
        if self.doc and self.current_page < self._total_pages - 1:
            self.current_page += 1
            self._update_toolbar()
            if not self._continuous_mode:
                self._render_single()
            else:
                self._scroll_to_current_page()

    def prev_page(self):
        if self.doc and self.current_page > 0:
            self.current_page -= 1
            self._update_toolbar()
            if not self._continuous_mode:
                self._render_single()
            else:
                self._scroll_to_current_page()

    def zoom_in(self):
        self._scale *= 1.2
        self._invalidate_and_reload()

    def zoom_out(self):
        self._scale /= 1.2
        self._invalidate_and_reload()

    def _invalidate_and_reload(self):
        """缩放后重建所有渲染状态。"""
        if self.doc is None:
            return
        self._stop_background()
        self._page_cache.clear()
        self._pending_indices.clear()
        self._all_indices_rendered = False
        self._rendered_count = 0
        self._precompute_page_sizes()
        self.progress.setMaximum(self._total_pages)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self._render()

    def close_document(self):
        self._stop_background()
        self._clear_visible_widgets()
        if self.doc:
            self.doc.close()
            self.doc = None
        self._page_cache.clear()
        self._page_heights.clear()
        self._page_widths.clear()
        self._update_toolbar()

    def eventFilter(self, obj, event):
        """拦截 scroll viewport 的 resize 事件。"""
        if obj is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._on_viewport_resize()
        return super().eventFilter(obj, event)
