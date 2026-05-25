"""分子提取人工确认对话框.

对 MolDetv2 + MolScribe 检测到的候选分子进行人工审核：
- 查看分子图像与识别结果
- 编辑/修正 SMILES
- 确认入库或丢弃
- 支持批量导航
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..parsers.extraction_result import ExtractionResult
from ..utils.logger import get_logger
from .theme import ThemeManager, _p, create_button, create_input, create_label

logger = get_logger(__name__)


class MoleculeExtractDialog(QDialog):
    """分子提取人工确认对话框.

    Signals:
        molecule_confirmed: 用户确认入库一个分子（返回修正后的 ExtractionResult）
        molecule_rejected: 用户丢弃一个分子（返回 mol_id 或 index）
        batch_finished: 批量处理完成
    """

    #: 用户确认入库一个分子（参数: 修正后的 ExtractionResult）
    molecule_confirmed = pyqtSignal(object)
    #: 用户丢弃一个分子（参数: 被丢弃的 ExtractionResult）
    molecule_rejected = pyqtSignal(object)
    #: 批量处理完成（无论是否全部审核完毕）
    batch_finished = pyqtSignal()

    def __init__(
        self,
        results: list[ExtractionResult],
        parent: QWidget | None = None,
    ):
        """初始化对话框.

        Args:
            results: 待确认的 ExtractionResult 列表
            parent: 父窗口
        """
        super().__init__(parent)
        self.results = results
        self.current_idx = 0
        self.confirmed_count = 0
        self.rejected_count = 0

        self.setWindowTitle("分子提取确认")
        self.setMinimumSize(900, 650)
        ThemeManager.apply_dialog(self)
        self._setup_ui()
        self._load_current()

    def _setup_ui(self):
        """构建 UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        p = _p()

        # ---- 顶部标题栏 ----
        header = QHBoxLayout()
        self.title_label = create_label("分子提取确认", level="header")
        header.addWidget(self.title_label)

        self.progress_label = create_label("0 / 0", level="caption")
        self.progress_label.setStyleSheet(
            f"color: {p['text_secondary']}; padding: 4px 12px;"
        )
        header.addWidget(self.progress_label)
        header.addStretch()

        # 统计
        self.stats_label = create_label("已确认: 0 | 已丢弃: 0", level="caption")
        self.stats_label.setStyleSheet(f"color: {p['text_secondary']};")
        header.addWidget(self.stats_label)
        layout.addLayout(header)

        # ---- 主体：左图右信息 ----
        body = QHBoxLayout()
        body.setSpacing(16)

        # 左侧：图像 + 导航
        left = QVBoxLayout()
        left.setSpacing(8)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(400, 400)
        self.image_label.setStyleSheet(
            f"background: {p['bg_card']}; border-radius: 8px; "
            f"border: 1px solid {p['border']};"
        )
        left.addWidget(self.image_label, stretch=1)

        # 导航按钮
        nav = QHBoxLayout()
        self.prev_btn = create_button("← 上一个")
        self.prev_btn.clicked.connect(self._go_previous)
        nav.addWidget(self.prev_btn)

        nav.addStretch()

        self.next_btn = create_button("下一个 →")
        self.next_btn.clicked.connect(self._go_next)
        nav.addWidget(self.next_btn)
        left.addLayout(nav)

        body.addLayout(left, stretch=1)

        # 右侧：信息面板
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        right_widget = QWidget()
        right = QVBoxLayout(right_widget)
        right.setSpacing(10)
        right.setContentsMargins(8, 8, 8, 8)

        # 页面位置
        self.page_info = create_label("", level="caption")
        self.page_info.setStyleSheet(f"color: {p['accent']};")
        right.addWidget(self.page_info)

        # SMILES（可编辑）
        right.addWidget(create_label("SMILES", level="subheader"))
        self.smiles_edit = create_input()
        self.smiles_edit.setMinimumHeight(36)
        right.addWidget(self.smiles_edit)

        # 名称（可编辑）
        right.addWidget(create_label("化合物名称", level="subheader"))
        self.name_edit = create_input()
        self.name_edit.setPlaceholderText("自动识别或手动输入...")
        right.addWidget(self.name_edit)

        # 置信度信息
        right.addWidget(create_label("识别置信度", level="subheader"))
        self.conf_label = create_label("", level="body")
        self.conf_label.setWordWrap(True)
        self.conf_label.setStyleSheet(
            f"padding: 8px; background: {p['bg_hover']}; "
            f"border-radius: 6px; border: 1px solid {p['border']};"
        )
        right.addWidget(self.conf_label)

        # 上下文文本
        right.addWidget(create_label("附近文本", level="subheader"))
        self.context_text = QTextEdit()
        self.context_text.setReadOnly(True)
        self.context_text.setMaximumHeight(120)
        self.context_text.setStyleSheet(
            f"background: {p['bg_card']}; border-radius: 6px; "
            f"border: 1px solid {p['border']}; padding: 6px;"
        )
        right.addWidget(self.context_text)

        # 属性信息
        right.addWidget(create_label("关联属性", level="subheader"))
        self.props_label = create_label("", level="body")
        self.props_label.setWordWrap(True)
        self.props_label.setStyleSheet(
            f"padding: 8px; background: {p['bg_hover']}; "
            f"border-radius: 6px; border: 1px solid {p['border']};"
        )
        right.addWidget(self.props_label)

        right.addStretch()
        right_scroll.setWidget(right_widget)
        body.addWidget(right_scroll, stretch=1)

        layout.addLayout(body, stretch=1)

        # ---- 底部操作按钮 ----
        footer = QHBoxLayout()
        footer.setSpacing(12)

        self.reject_btn = create_button("丢弃")
        self.reject_btn.setStyleSheet(
            f"background: {p['error']}; color: white; padding: 8px 20px;"
        )
        self.reject_btn.clicked.connect(self._reject_current)
        footer.addWidget(self.reject_btn)

        footer.addStretch()

        self.edit_btn = create_button("编辑 SMILES")
        self.edit_btn.clicked.connect(self._focus_smiles)
        footer.addWidget(self.edit_btn)

        self.confirm_btn = create_button("确认入库")
        self.confirm_btn.setStyleSheet(
            f"background: {p['success']}; color: white; padding: 8px 20px;"
        )
        self.confirm_btn.clicked.connect(self._confirm_current)
        footer.addWidget(self.confirm_btn)

        layout.addLayout(footer)

        # 一键完成
        finish = QHBoxLayout()
        finish.addStretch()
        self.finish_btn = create_button("完成审核")
        self.finish_btn.clicked.connect(self._finish_batch)
        finish.addWidget(self.finish_btn)
        layout.addLayout(finish)

    def _load_current(self):
        """加载当前索引的分子数据."""
        if not self.results:
            self._show_empty_state()
            return

        result = self.results[self.current_idx]

        # 更新标题和进度
        total = len(self.results)
        self.progress_label.setText(f"{self.current_idx + 1} / {total}")
        self.title_label.setText(f"分子提取确认 — #{self.current_idx + 1}")

        # 页面位置
        page_text = f"PDF 第 {result.page_idx + 1} 页" if result.page_idx is not None else "未知页面"
        self.page_info.setText(page_text)

        # 加载图像
        self._load_image(result.mol_img_path)

        # 填充文本
        self.smiles_edit.setText(result.smiles)
        self.name_edit.setText(result.name)

        # 置信度
        conf_lines = [
            f"• 检测置信度: {result.moldet_conf:.3f}",
            f"• 识别置信度: {result.scribe_conf:.3f}",
            f"• 综合置信度: {result.composite_conf:.3f}",
        ]
        self.conf_label.setText("\n".join(conf_lines))

        # 上下文
        self.context_text.setText(result.context_text or "（无附近文本）")

        # 属性
        props_lines = []
        if result.properties:
            for k, v in result.properties.items():
                if k == "activities" and isinstance(v, list):
                    for act in v:
                        props_lines.append(
                            f"• {act['type']}: {act['value']} {act['unit']}"
                        )
                elif k not in ("activities",):
                    props_lines.append(f"• {k}: {v}")
        self.props_label.setText(
            "\n".join(props_lines) if props_lines else "（无关联属性）"
        )

        # 更新导航按钮状态
        self.prev_btn.setEnabled(self.current_idx > 0)
        self.next_btn.setEnabled(self.current_idx < total - 1)

        # 更新统计
        self.stats_label.setText(
            f"已确认: {self.confirmed_count} | 已丢弃: {self.rejected_count}"
        )

    def _load_image(self, img_path: Path | None):
        """加载分子图像."""
        if img_path and Path(img_path).exists():
            pixmap = QPixmap(str(img_path))
            if not pixmap.isNull():
                # 等比缩放适配标签
                scaled = pixmap.scaled(
                    self.image_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.image_label.setPixmap(scaled)
                return
        self.image_label.setText("（无图像）")

    def _show_empty_state(self):
        """无数据时的空状态."""
        self.image_label.setText("（无待确认分子）")
        self.smiles_edit.clear()
        self.name_edit.clear()
        self.conf_label.setText("")
        self.context_text.clear()
        self.props_label.setText("")
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.confirm_btn.setEnabled(False)
        self.reject_btn.setEnabled(False)

    def _go_previous(self):
        """上一个."""
        if self.current_idx > 0:
            self.current_idx -= 1
            self._load_current()

    def _go_next(self):
        """下一个."""
        if self.current_idx < len(self.results) - 1:
            self.current_idx += 1
            self._load_current()

    def _confirm_current(self):
        """确认当前分子入库."""
        if not self.results:
            return
        result = self.results[self.current_idx]
        # 更新用户编辑后的值
        result.smiles = self.smiles_edit.text().strip()
        result.name = self.name_edit.text().strip()
        result.status = "confirmed"
        self.confirmed_count += 1
        self.molecule_confirmed.emit(result)
        logger.info("分子已确认: %s", result.smiles[:40])
        self._advance()

    def _reject_current(self):
        """丢弃当前分子."""
        if not self.results:
            return
        result = self.results[self.current_idx]
        result.status = "rejected"
        self.rejected_count += 1
        self.molecule_rejected.emit(result)
        logger.info("分子已丢弃: %s", result.smiles[:40])
        self._advance()

    def _advance(self):
        """自动前进到下一个未处理的分子."""
        total = len(self.results)
        # 从当前位置向后找第一个 pending 的
        for i in range(self.current_idx + 1, total):
            if self.results[i].status == "pending":
                self.current_idx = i
                self._load_current()
                return
        # 向前找
        for i in range(0, self.current_idx):
            if self.results[i].status == "pending":
                self.current_idx = i
                self._load_current()
                return
        # 全部处理完毕
        self._show_completion()

    def _show_completion(self):
        """全部处理完毕提示."""
        QMessageBox.information(
            self,
            "审核完成",
            f"全部 {len(self.results)} 个分子已处理完毕。\n"
            f"已确认: {self.confirmed_count} 个\n"
            f"已丢弃: {self.rejected_count} 个",
        )
        self.batch_finished.emit()
        self.accept()

    def _focus_smiles(self):
        """聚焦到 SMILES 编辑框."""
        self.smiles_edit.setFocus()
        self.smiles_edit.selectAll()

    def _finish_batch(self):
        """提前结束批量审核."""
        pending = sum(1 for r in self.results if r.status == "pending")
        if pending > 0:
            reply = QMessageBox.question(
                self,
                "确认结束",
                f"还有 {pending} 个分子未处理，确定结束审核？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.batch_finished.emit()
        self.accept()

    def resizeEvent(self, event):
        """窗口大小变化时重新缩放图像（仅在尺寸显著变化时重载）."""
        super().resizeEvent(event)
        if not self.results or self.current_idx >= len(self.results):
            return
        new_size = self.image_label.size()
        # 避免微小抖动触发重载
        if hasattr(self, "_last_image_size"):
            old_w, old_h = self._last_image_size
            if abs(new_size.width() - old_w) < 20 and abs(new_size.height() - old_h) < 20:
                return
        self._last_image_size = (new_size.width(), new_size.height())
        self._load_image(self.results[self.current_idx].mol_img_path)
