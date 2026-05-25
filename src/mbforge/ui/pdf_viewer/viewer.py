"""PDF 查看器主类 — 支持大文档虚拟滚动 + 分片切片按需加载."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

import fitz  # PyMuPDF
from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal, pyqtSlot, QRect
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mbforge.utils.logger import get_logger, log_exception

from PIL import Image

from .page_widget import PDFPageLabel
from .renderer import _executor, _NWORKERS, _render_page_batch, page_to_pixmap
from .slice_manager import PDFSliceManager
from ..mol_extract_dialog import MoleculeExtractDialog
from ..theme import ThemeManager

if TYPE_CHECKING:
    from ...parsers.mol_image_pipeline import MolImagePipeline
    from ...parsers.extraction_result import ExtractionResult

logger = get_logger(__name__)


class PDFViewer(QWidget):
    """基于 PyMuPDF 的 PDF 查看器（虚拟滚动连续模式 + 大文件分片）."""

    logger = get_logger(__name__ + ".PDFViewer")

    page_changed = pyqtSignal(int, int)  # current, total
    _pages_done = pyqtSignal(list)  # 内部信号，在主线程触发 _on_pages_ready

    # 虚拟滚动缓冲：视口上下各额外渲染 N 页
    BUFFER_PAGES = 5
    MAX_CACHE_PAGES = 20  # 内存 LRU 缓存上限

    def __init__(
        self,
        parent: QWidget | None = None,
        mol_image_pipeline: MolImagePipeline | None = None,
    ):
        super().__init__(parent)
        self.doc: fitz.Document | None = None
        self._doc_path: str | None = None
        self._slice_manager: PDFSliceManager | None = None
        self._use_slices: bool = False
        self.current_page = 0
        self._scale = 1.5
        self.mol_image_pipeline = mol_image_pipeline

        # 虚拟滚动状态
        self._continuous_mode = True
        self._virtual_container: QWidget | None = None
        self._page_heights: list[int] = []
        self._page_widths: list[int] = []
        self._page_cache: OrderedDict[int, QPixmap] = OrderedDict()
        self._visible_widgets: OrderedDict[
            int, tuple[QLabel, QLabel]
        ] = OrderedDict()
        self._pending_indices: set = set()
        self._all_indices_rendered: bool = False

        self._rendered_count = 0
        self._total_pages = 0

        # 高亮注释
        self._annotations: dict[int, list[dict]] = {}
        self._annotation_file: Path | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ---- 工具栏 ----
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 4, 8, 4)

        self.btn_mode = QPushButton("连续模式")
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
        p = ThemeManager.instance().palette()
        self.page_label.setStyleSheet(f"font-size: 13px; color: {p['text_primary']};")
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

        btn_zoom_out = QPushButton("−")
        btn_zoom_out.setToolTip("缩小")
        btn_zoom_out.clicked.connect(self.zoom_out)
        toolbar.addWidget(btn_zoom_out)

        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setToolTip("放大")
        btn_zoom_in.clicked.connect(self.zoom_in)
        toolbar.addWidget(btn_zoom_in)

        btn_clear_highlight = QPushButton("✨ 清除高亮")
        btn_clear_highlight.setToolTip("清除所有高亮注释")
        btn_clear_highlight.clicked.connect(self._clear_all_highlights)
        toolbar.addWidget(btn_clear_highlight)

        layout.addLayout(toolbar)

        # ---- 滚动区域 ----
        self.scroll = QScrollArea()
        # 注意：连续模式下 _virtual_container 没有 layout，子 widget 手动定位，
        # 因此 widgetResizable 必须为 False，否则 QScrollArea 会自动 resize widget
        # 导致子 widget 位置被覆盖或 clipping 异常。
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        p = ThemeManager.instance().palette()
        self.scroll.setStyleSheet(
            f"background: {p['bg_base']}; border: 1px solid {p['border']}; border-radius: 10px;"
        )
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.scroll.viewport().installEventFilter(self)

        self.single_label: QLabel | None = None
        self.scroll.setWidget(self.single_label)
        layout.addWidget(self.scroll, 1)

        self._pages_done.connect(
            self._on_pages_ready, Qt.ConnectionType.QueuedConnection
        )
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _stop_background(self):
        """取消在途渲染任务。"""
        self._pending_indices.clear()

    def _toggle_mode(self):
        self._continuous_mode = not self._continuous_mode
        self.logger.info(f"_toggle_mode | continuous={self._continuous_mode}")
        self.btn_mode.setText("连续模式" if self._continuous_mode else "单页模式")
        self._render()

    def load_pdf(self, path: Path, project_root: Path | None = None):
        """加载PDF文件。如果提供project_root且文件较大，自动启用分片模式。"""
        self.logger.info(f"load_pdf | path={path} | project_root={project_root}")
        self._stop_background()
        self.close_document()
        p = ThemeManager.instance().palette()

        self._doc_path = str(path.resolve())

        # 尝试启用分片模式
        self._use_slices = False
        self._slice_manager = None
        if project_root is not None:
            self.logger.debug("尝试启用分片模式...")
            self._slice_manager = PDFSliceManager(path, project_root)
            self._use_slices = self._slice_manager.ensure_sliced()
            self.logger.info(f"分片模式={'启用' if self._use_slices else '未启用'} | 总页数={self._slice_manager.total_pages if self._slice_manager else 'N/A'}")

        if self._use_slices:
            self._total_pages = self._slice_manager.total_pages
        else:
            # 回退到原始模式：直接打开完整PDF
            self.logger.debug("回退到原始模式，打开完整PDF")
            self.doc = fitz.open(str(path))
            self._total_pages = len(self.doc)

        # 添加空白第0页（封面）
        self._total_pages += 1

        self.current_page = 0
        self._page_cache.clear()
        self._visible_widgets.clear()
        self._pending_indices.clear()
        self._all_indices_rendered = False
        self._rendered_count = 0

        # 初始化注释
        self._annotations = {}
        self._annotation_file = None
        if project_root is not None and self._doc_path:
            mtime = path.stat().st_mtime
            hash_input = f"{path.resolve()}:{mtime}"
            doc_hash = hashlib.md5(hash_input.encode()).hexdigest()[:16]
            self._annotation_file = (
                project_root / ".mbforge" / "pdf_annotations" / f"{doc_hash}.json"
            )
            self._load_annotations()

        try:
            self._precompute_page_sizes()
            self.logger.debug(f"预计算页尺寸完成: {self._total_pages} 页 | 总高度={self._total_height()}")
            self._render()
        except Exception:
            log_exception(self.logger, f"PDF加载失败: {path}")
            self._clear_visible_widgets()
            self.single_label = QLabel()
            self.single_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.single_label.setStyleSheet(f"background: {p['bg_base']}; border-radius: 10px;")
            self.single_label.setText("无法加载 PDF: 详见日志")
            self.scroll.setWidget(self.single_label)

    def _precompute_page_sizes(self):
        """预先计算每页渲染尺寸。分片模式下直接读metadata，无需打开PDF.

        注意：结果包含开头的空白第0页。
        """
        self._page_heights = []
        self._page_widths = []

        if self._use_slices and self._slice_manager is not None:
            for raw_w, raw_h in self._slice_manager.page_sizes:
                w = int(raw_w * self._scale)
                h = int(raw_h * self._scale)
                self._page_heights.append(h + 30)  # 页码标签高度
                self._page_widths.append(w)
        else:
            for i in range(len(self.doc)):
                rect = self.doc[i].mediabox
                w = int(rect.width * self._scale)
                h = int(rect.height * self._scale)
                self._page_heights.append(h + 30)
                self._page_widths.append(w)

        # 在开头插入空白第0页（封面）
        blank_w = max(self._page_widths) if self._page_widths else 400
        blank_h = 400
        self._page_heights.insert(0, blank_h + 30)
        self._page_widths.insert(0, blank_w)

    def _total_height(self) -> int:
        return sum(self._page_heights)

    def _render(self):
        if not self._use_slices and self.doc is None:
            return
        if self._use_slices and self._slice_manager is None:
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
        self.logger.debug("_render_continuous_virtual 开始")
        self._clear_visible_widgets()

        self._virtual_container = QWidget()
        # 先 setWidget，再设置大小。QScrollArea 会根据 widget 的 size/minimumSize
        # 计算滚动条范围。setMinimumSize 足够让 scroll area 知道总高度。
        self.scroll.setWidget(self._virtual_container)
        container_w = max(self._page_widths) if self._page_widths else 400
        container_h = self._total_height() if self._page_heights else 600
        # widgetResizable=False 时 QScrollArea 使用实际尺寸计算滚动范围，
        # 因此必须同时设置 fixedSize，否则容器尺寸为默认值导致子 widget 被裁剪。
        self._virtual_container.setFixedSize(container_w, container_h)
        self.logger.debug(f"虚拟容器大小: {container_w}x{container_h}")
        # 强制背景色，避免透明导致看不清
        p = ThemeManager.instance().palette()
        self._virtual_container.setStyleSheet(f"background: {p['bg_card']};")
        self.scroll.verticalScrollBar().setValue(0)

        vp = self.scroll.viewport()
        self.logger.debug(f"viewport 大小: {vp.width()}x{vp.height()}")

        self._render_visible_range()
        self.page_changed.emit(self.current_page + 1, self._total_pages)
        self.logger.debug(f"_render_continuous_virtual 完成 | visible_widgets={len(self._visible_widgets)}")
        QTimer.singleShot(0, self._rerender_if_needed)

    def _render_visible_range(self):
        """根据当前滚动位置，渲染可见页范围内所有页，回收范围外页。"""
        if not self._virtual_container:
            return

        vp = self.scroll.viewport()
        scroll_y = self.scroll.verticalScrollBar().value()
        vis_top = scroll_y
        vis_bottom = scroll_y + vp.height()

        # 保底：viewport 还没布局好时（height=0），至少渲染首屏前几页
        if vp.height() <= 0:
            start_idx = 0
            end_idx = min(self._total_pages - 1, self.BUFFER_PAGES)
        else:
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
            # 先解除 parent 关系再 deleteLater，避免 parent 析构时二次释放
            w_num.setParent(None)
            w_num.deleteLater()
            w_img.setParent(None)
            w_img.deleteLater()

        # 渲染范围内缺失的页
        to_render: list[int] = []
        for i in range(start_idx, end_idx + 1):
            if i not in self._visible_widgets and i not in self._pending_indices:
                if i in self._page_cache:
                    self._place_page_widget(i, self._page_cache[i])
                else:
                    to_render.append(i)

        if to_render:
            for idx in to_render:
                self._render_page_sync(idx)

        still_missing = [idx for idx in to_render if idx not in self._page_cache]
        if still_missing and not self._all_indices_rendered:
            self._start_background_render(still_missing)

    def _render_page_sync(self, index: int) -> bool:
        """同步渲染单页，返回是否成功。"""
        if index in self._page_cache:
            return False

        # 空白第0页
        if index == 0:
            blank_w = self._page_widths[0] if self._page_widths else 400
            blank_h = self._page_heights[0] - 30 if self._page_heights else 370
            pm = QPixmap(blank_w, blank_h)
            pm.fill(Qt.GlobalColor.white)
            self._add_to_cache(0, pm)
            self._place_page_widget(0, pm)
            self._rendered_count += 1
            self.logger.debug("第 0 页（空白封面）渲染成功")
            return True

        pdf_index = index - 1  # 实际PDF页码偏移1
        try:
            if self._use_slices and self._slice_manager is not None:
                slice_path = str(self._slice_manager.get_slice_path(pdf_index))
                local_idx = self._slice_manager.get_local_index(pdf_index)
                self.logger.debug(f"渲染第 {index} 页 | 分片={slice_path} | 局部页码={local_idx}")
                doc = fitz.open(slice_path)
                try:
                    page = doc[local_idx]
                    img = page_to_pixmap(page, self._scale)
                finally:
                    doc.close()
            else:
                self.logger.debug(f"渲染第 {index} 页 | 原始模式")
                page = self.doc[pdf_index]
                img = page_to_pixmap(page, self._scale)

            pm = QPixmap.fromImage(img)
            pm = self._apply_annotations_to_pixmap(pm, index)
            self._add_to_cache(index, pm)
            self._place_page_widget(index, pm)
            self._rendered_count += 1
            self.logger.debug(f"第 {index} 页渲染成功")
            return True
        except Exception:
            log_exception(self.logger, f"第 {index} 页渲染失败")
            return False

    def _place_page_widget(self, index: int, pixmap: QPixmap):
        """将渲染好的 pixmap 放入虚拟容器的正确位置。"""
        if index in self._visible_widgets or not self._virtual_container:
            return

        p = ThemeManager.instance().palette()
        label_text = "— 第 0 页（空白封面） —" if index == 0 else f"— 第 {index} 页 —"
        num_label = QLabel(label_text, self._virtual_container)
        num_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num_label.setStyleSheet(f"color: {p['text_secondary']}; font-size: 12px; padding: 4px;")
        num_label.move(0, self._page_offset(index))
        num_label.resize(max(self._page_widths), 25)
        num_label.show()

        img_label = PDFPageLabel(index, self._virtual_container)
        img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_label.setPixmap(pixmap)
        img_label.setFixedSize(pixmap.width(), pixmap.height())
        img_label.setStyleSheet(
            f"background: {p['bg_card']}; border: 1px solid {p['border']}; border-radius: 4px;"
        )
        if index != 0:
            img_label.highlight_requested.connect(self._on_highlight)
            img_label.clear_highlights_requested.connect(self._clear_page_highlights)
            img_label.copy_text_requested.connect(self._on_copy_selection)
            img_label.molecule_extract_requested.connect(self._on_extract_molecule)
        img_label.move(0, self._page_offset(index) + 25)
        img_label.resize(pixmap.width(), pixmap.height())
        img_label.show()

        self._visible_widgets[index] = (num_label, img_label)

    def _page_offset(self, index: int) -> int:
        """第 index 页相对于容器顶部的 Y 偏移。"""
        return sum(self._page_heights[:index])

    def _start_background_render(self, indices: list[int]):
        """使用线程池并行渲染指定页。"""
        # 排除空白第0页，它不需要后台渲染
        indices = [idx for idx in indices if idx != 0]
        if not indices:
            return
        self._pending_indices.update(indices)

        if self._use_slices and self._slice_manager is not None:
            # 按分片路径分组，每分片一批提交给worker
            slice_groups: dict[str, list[tuple[int, int]]] = defaultdict(list)
            for global_idx in indices:
                slice_path = str(self._slice_manager.get_slice_path(global_idx))
                local_idx = self._slice_manager.get_local_index(global_idx)
                slice_groups[slice_path].append((local_idx, global_idx))

            self.progress.setMaximum(len(indices))
            self.progress.setVisible(True)

            for slice_path, items in slice_groups.items():
                _executor.submit(
                    _render_page_batch, slice_path, self._scale, items
                ).add_done_callback(self._on_future_done)
        else:
            # 原始模式：直接按原始PDF提交
            n = min(len(indices), _NWORKERS)
            chunk_size = max(1, len(indices) // n)
            chunks = [
                indices[i : i + chunk_size] for i in range(0, len(indices), chunk_size)
            ]
            self.progress.setMaximum(self._total_pages)
            self.progress.setVisible(True)
            for chunk in chunks:
                items = [(idx, idx) for idx in chunk]
                _executor.submit(
                    _render_page_batch, self._doc_path, self._scale, items
                ).add_done_callback(self._on_future_done)

    def _on_future_done(self, future):
        """线程池 future 完成回调，通过信号切回主线程。"""
        try:
            results = future.result()
        except Exception:
            return
        self._pages_done.emit(results)

    @pyqtSlot(list)
    def _on_pages_ready(self, batch: list):
        """主线程收到渲染好的页，转为 QPixmap 并放入缓存和 UI。"""
        if not batch:
            return
        for idx, qimage in batch:
            if idx in self._pending_indices:
                self._pending_indices.discard(idx)
            if idx not in self._page_cache:
                pm = QPixmap.fromImage(qimage)
                pm = self._apply_annotations_to_pixmap(pm, idx)
                self._add_to_cache(idx, pm)
                self._rendered_count += 1
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
            self.logger.debug("_on_scroll")
            self._render_visible_range()

    def _on_viewport_resize(self):
        """窗口大小变化时重新计算可见范围。"""
        if self._continuous_mode and self._virtual_container:
            self.logger.debug("_on_viewport_resize")
            self._render_visible_range()

    def _rerender_if_needed(self):
        """布局完成后检查：若首屏未渲染则重新渲染。"""
        if (
            self._continuous_mode
            and self._virtual_container
            and not self._visible_widgets
        ):
            self.logger.debug("_rerender_if_needed | 首屏未渲染，重新渲染")
            self._render_visible_range()

    def _render_single(self):
        """单页模式（按需渲染，无虚拟滚动开销）。"""
        self.logger.debug(f"_render_single | page={self.current_page}")
        self._clear_visible_widgets()
        p = ThemeManager.instance().palette()
        self.single_label = PDFPageLabel(self.current_page)
        self.single_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.single_label.setStyleSheet(f"background: {p['bg_base']}; border-radius: 10px;")
        self.scroll.setWidget(self.single_label)
        self.single_label.clear()
        if self.current_page != 0:
            self.single_label.highlight_requested.connect(self._on_highlight)
            self.single_label.clear_highlights_requested.connect(self._clear_page_highlights)
            self.single_label.copy_text_requested.connect(self._on_copy_selection)
            self.single_label.molecule_extract_requested.connect(self._on_extract_molecule)

        try:
            if self.current_page == 0:
                # 空白第0页（封面）
                blank_w = self._page_widths[0] if self._page_widths else 400
                blank_h = self._page_heights[0] - 30 if self._page_heights else 370
                pm = QPixmap(blank_w, blank_h)
                pm.fill(Qt.GlobalColor.white)
                pm = self._apply_annotations_to_pixmap(pm, self.current_page)
                self.single_label.setPixmap(pm)
                self.single_label.setFixedSize(pm.width(), pm.height())
            elif self._use_slices and self._slice_manager is not None:
                pdf_index = self.current_page - 1
                slice_path = str(self._slice_manager.get_slice_path(pdf_index))
                local_idx = self._slice_manager.get_local_index(pdf_index)
                doc = fitz.open(slice_path)
                try:
                    page = doc[local_idx]
                    img = page_to_pixmap(page, self._scale)
                finally:
                    doc.close()
                pm = QPixmap.fromImage(img)
                pm = self._apply_annotations_to_pixmap(pm, self.current_page)
                self.single_label.setPixmap(pm)
                self.single_label.setFixedSize(pm.width(), pm.height())
            else:
                pdf_index = self.current_page - 1
                page = self.doc[pdf_index]
                img = page_to_pixmap(page, self._scale)
                pm = QPixmap.fromImage(img)
                pm = self._apply_annotations_to_pixmap(pm, self.current_page)
                self.single_label.setPixmap(pm)
                self.single_label.setFixedSize(pm.width(), pm.height())
        except Exception:
            self.single_label.setText(f"无法渲染第 {self.current_page} 页")

        self.page_changed.emit(self.current_page + 1, self._total_pages)

    def _add_to_cache(self, index: int, pixmap: QPixmap) -> None:
        """将 pixmap 加入 LRU 缓存，超出上限时移除最旧项。"""
        self._page_cache[index] = pixmap
        self._page_cache.move_to_end(index)
        while len(self._page_cache) > self.MAX_CACHE_PAGES:
            oldest_idx, oldest_pm = self._page_cache.popitem(last=False)
            if oldest_idx in self._visible_widgets:
                self._page_cache[oldest_idx] = oldest_pm
                break

    def _clear_visible_widgets(self):
        """清空虚拟滚动容器中的所有子 widget。"""
        # 不单独 deleteLater 子 widget，parent 删除时会自动级联删除。
        # 否则 parent 的析构可能访问已释放的子对象，导致段错误/闪退。
        self._visible_widgets.clear()
        if self._virtual_container:
            # 先从 scroll area 中安全移除，避免 setWidget() 时访问已标记删除的对象
            if self.scroll.widget() is self._virtual_container:
                self.scroll.takeWidget()
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
            self._has_document() and self.current_page > 0 and not self._continuous_mode
        )
        self.btn_next.setEnabled(
            self._has_document()
            and self.current_page < total - 1
            and not self._continuous_mode
        )
        self.page_label.setText(f"第 {current} / {total} 页")
        self.page_input.setMaximum(total)
        self.page_input.setValue(current)

    def _has_document(self) -> bool:
        """检查当前是否有可渲染的文档。"""
        return self._use_slices or self.doc is not None

    def _jump_to_page_input(self):
        if not self._has_document():
            return
        page = self.page_input.value() - 1
        if 0 <= page < self._total_pages:
            self.current_page = page
            self.logger.info(f"_jump_to_page_input | page={self.current_page}")
            if self._continuous_mode and self._virtual_container:
                target_y = self._page_offset(page)
                self.scroll.verticalScrollBar().setValue(target_y)
            else:
                self._render_single()
            self._update_toolbar()

    def next_page(self):
        if self._has_document() and self.current_page < self._total_pages - 1:
            self.current_page += 1
            self.logger.debug(f"next_page | page={self.current_page}")
            self._update_toolbar()
            if not self._continuous_mode:
                self._render_single()
            else:
                self._scroll_to_current_page()

    def prev_page(self):
        if self._has_document() and self.current_page > 0:
            self.current_page -= 1
            self.logger.debug(f"prev_page | page={self.current_page}")
            self._update_toolbar()
            if not self._continuous_mode:
                self._render_single()
            else:
                self._scroll_to_current_page()

    def zoom_in(self):
        self._scale *= 1.2
        self.logger.info(f"zoom_in | scale={self._scale:.2f}")
        self._invalidate_and_reload()

    def zoom_out(self):
        self._scale /= 1.2
        self.logger.info(f"zoom_out | scale={self._scale:.2f}")
        self._invalidate_and_reload()

    def _invalidate_and_reload(self):
        """缩放后重建所有渲染状态。"""
        if not self._has_document():
            return
        self.logger.info("_invalidate_and_reload | 重建渲染状态")
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

    # ---- 高亮注释功能 ----

    def _apply_annotations_to_pixmap(
        self, pixmap: QPixmap, page_index: int
    ) -> QPixmap:
        """在渲染好的 pixmap 上叠加高亮注释."""
        anns = self._annotations.get(page_index, [])
        if not anns:
            return pixmap
        new_pm = QPixmap(pixmap)
        painter = QPainter(new_pm)
        for ann in anns:
            if ann.get("type") == "highlight":
                r = ann["rect"]
                x0 = int(r[0] * self._scale)
                y0 = int(r[1] * self._scale)
                x1 = int(r[2] * self._scale)
                y1 = int(r[3] * self._scale)
                color = ann.get("color", [1.0, 1.0, 0.0])
                qcolor = QColor(
                    int(color[0] * 255),
                    int(color[1] * 255),
                    int(color[2] * 255),
                    80,
                )
                painter.fillRect(QRect(x0, y0, x1 - x0, y1 - y0), qcolor)
        painter.end()
        return new_pm

    def _on_highlight(self, page_index: int, screen_rect: QRect):
        """处理划词高亮请求.

        坐标转换假设：self._scale 等于当前渲染的 像素/点 比例
        （即 page.get_pixmap(dpi=72*scale).width / page.rect.width）。
        因此 screen_rect(像素) / scale 即为 PDF 点坐标。
        """
        if page_index == 0:
            return
        pdf_index = page_index - 1
        pdf_rect = fitz.Rect(
            screen_rect.left() / self._scale,
            screen_rect.top() / self._scale,
            screen_rect.right() / self._scale,
            screen_rect.bottom() / self._scale,
        )
        text = self._get_text_in_rect(pdf_index, pdf_rect)
        ann = {
            "type": "highlight",
            "rect": [pdf_rect.x0, pdf_rect.y0, pdf_rect.x1, pdf_rect.y1],
            "text": text,
            "color": [1.0, 1.0, 0.0],
        }
        if page_index not in self._annotations:
            self._annotations[page_index] = []
        self._annotations[page_index].append(ann)
        self._save_annotations()
        self.logger.info(f"高亮注释: page={page_index}, text={text[:50]}...")
        # 重新渲染该页以显示高亮
        if page_index in self._page_cache:
            del self._page_cache[page_index]
        if page_index in self._visible_widgets:
            w_num, w_img = self._visible_widgets.pop(page_index)
            w_num.setParent(None)
            w_num.deleteLater()
            w_img.setParent(None)
            w_img.deleteLater()
        self._render_page_sync(page_index)

    def _get_text_in_rect(self, pdf_index: int, pdf_rect: fitz.Rect) -> str:
        """在指定PDF页的指定矩形区域内提取文本."""
        try:
            if self.doc:
                page = self.doc[pdf_index]
                return page.get_text("text", clip=pdf_rect).strip()[:500]
            elif self._doc_path:
                doc = fitz.open(self._doc_path)
                try:
                    page = doc[pdf_index]
                    return page.get_text("text", clip=pdf_rect).strip()[:500]
                finally:
                    doc.close()
        except Exception:
            log_exception(self.logger, "提取文本失败")
        return ""

    def _on_copy_selection(self, page_index: int, screen_rect: QRect):
        """复制选区内的文本到剪贴板."""
        if page_index == 0:
            return
        pdf_index = page_index - 1
        pdf_rect = fitz.Rect(
            screen_rect.left() / self._scale,
            screen_rect.top() / self._scale,
            screen_rect.right() / self._scale,
            screen_rect.bottom() / self._scale,
        )
        text = self._get_text_in_rect(pdf_index, pdf_rect)
        if text:
            from PyQt6.QtWidgets import QApplication

            QApplication.clipboard().setText(text)
            self.logger.info(f"复制文本: {text[:50]}...")

    def _on_extract_molecule(self, page_index: int, screen_rect: QRect):
        """识别选中区域内的分子结构."""
        if page_index == 0 or self.mol_image_pipeline is None:
            return
        if not self.mol_image_pipeline.is_available():
            QMessageBox.warning(
                self, "检测器不可用", "MolDetv2 模型未加载，无法识别分子。"
            )
            return

        pdf_index = page_index - 1
        try:
            page = self.doc[pdf_index]
            # 渲染整页图像（使用当前视图缩放）
            dpi = int(72 * self._scale)
            pix = page.get_pixmap(dpi=dpi)
            page_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # 屏幕坐标 → 图像坐标（PDFPageLabel 尺寸等于 pixmap 尺寸）
            x1 = int(screen_rect.left())
            y1 = int(screen_rect.top())
            x2 = int(screen_rect.right())
            y2 = int(screen_rect.bottom())
            crop_bbox = (x1, y1, x2, y2)

            result = self.mol_image_pipeline.extract_from_manual_crop(
                page_image=page_image,
                crop_bbox_img=crop_bbox,
                page_idx=pdf_index,
                page_w_pts=page.rect.width,
                page_h_pts=page.rect.height,
                image_w=pix.width,
                image_h=pix.height,
            )

            if not result.smiles:
                QMessageBox.information(
                    self, "未识别到分子", "选中区域内未识别到有效的分子结构。"
                )
                return

            dlg = MoleculeExtractDialog([result], parent=self)
            dlg.molecule_confirmed.connect(self._on_molecule_confirmed)
            dlg.exec()

        except Exception as exc:
            self.logger.error("分子识别失败: %s", exc)
            QMessageBox.critical(self, "识别失败", f"分子识别出错: {exc}")

    def _on_molecule_confirmed(self, result: ExtractionResult):
        """用户确认入库分子."""
        # TODO: 接入主应用的分子数据库
        self.logger.info(
            "用户确认入库分子: %s (source=%s)", result.smiles[:40], result.source
        )
        QMessageBox.information(
            self,
            "已确认",
            f"分子已确认:\nSMILES: {result.smiles[:60]}\n名称: {result.name or '-'}",
        )

    def _clear_page_highlights(self, page_index: int):
        """清除指定页面的所有高亮注释."""
        if page_index in self._annotations:
            del self._annotations[page_index]
            self._save_annotations()
            if page_index in self._page_cache:
                del self._page_cache[page_index]
            if page_index in self._visible_widgets:
                w_num, w_img = self._visible_widgets.pop(page_index)
                w_num.setParent(None)
                w_num.deleteLater()
                w_img.setParent(None)
                w_img.deleteLater()
            self._render_page_sync(page_index)
            self.logger.info(f"清除第 {page_index} 页高亮")

    def _clear_all_highlights(self):
        """清除所有高亮注释."""
        if not self._annotations:
            return
        reply = QMessageBox.question(
            self,
            "确认清除",
            "确定清除所有高亮注释？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._annotations.clear()
        self._save_annotations()
        self._invalidate_and_reload()
        self.logger.info("清除所有高亮注释")

    def _load_annotations(self):
        """从JSON文件加载注释."""
        if not self._annotation_file or not self._annotation_file.exists():
            return
        try:
            with open(self._annotation_file, encoding="utf-8") as f:
                data = json.load(f)
            self._annotations = {
                int(k): v for k, v in data.get("annotations", {}).items()
            }
            total = sum(len(v) for v in self._annotations.values())
            self.logger.info(f"加载 {total} 条注释")
        except Exception:
            log_exception(self.logger, "加载注释失败")
            self._annotations = {}

    def _save_annotations(self):
        """保存注释到JSON文件."""
        if not self._annotation_file:
            return
        try:
            self._annotation_file.parent.mkdir(parents=True, exist_ok=True)
            data = {"source": self._doc_path, "annotations": self._annotations}
            with open(self._annotation_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            log_exception(self.logger, "保存注释失败")

    def close_document(self):
        self.logger.info("close_document")
        self._stop_background()
        self._clear_visible_widgets()
        self._save_annotations()
        if self.doc:
            self.doc.close()
            self.doc = None
        self._slice_manager = None
        self._use_slices = False
        self._page_cache.clear()
        self._page_heights.clear()
        self._page_widths.clear()
        self._annotations.clear()
        self._annotation_file = None
        self._update_toolbar()

    def eventFilter(self, obj, event):
        """拦截 scroll viewport 的 resize 事件。"""
        if obj is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            self.logger.debug("viewport resize 事件")
            self._on_viewport_resize()
        return super().eventFilter(obj, event)

    def _on_theme_changed(self, mode: str):
        self.refresh()
