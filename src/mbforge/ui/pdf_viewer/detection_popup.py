"""检测框点击弹出面板 — 分子详情 / 编辑 / 批注."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
)

from ..components import BaseButton, InfoRow
from .annotations import DetectionBox
from ..theme import ThemeManager
from ..mol_renderer import MoleculeImageWidget


class DetectionPopup(QDialog):
    """点击检测框后弹出的分子详情/编辑面板."""

    edit_requested = pyqtSignal(str)  # detection_id
    status_changed = pyqtSignal(str, str)  # detection_id, new_status
    esmiles_saved = pyqtSignal(str, str)  # detection_id, esmiles
    comment_saved = pyqtSignal(str, str)  # detection_id, comment

    def __init__(self, detection_box: DetectionBox, parent=None):
        super().__init__(parent)
        self.detection = detection_box
        self.setWindowTitle("分子识别结果")
        self.setMinimumSize(420, 520)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # 1. 分子结构图
        self.img_widget = MoleculeImageWidget(self.detection.smiles, size=(380, 280))
        layout.addWidget(self.img_widget)

        # 2. 基本信息
        p = ThemeManager.instance().palette()
        layout.addWidget(InfoRow("SMILES", self.detection.smiles))

        # MolDet 置信度 — text_secondary
        moldet_row = InfoRow("MolDet 置信度", f"{self.detection.moldet_conf:.2f}")
        moldet_row.value_label.setStyleSheet(
            f"color: {p['text_secondary']}; font-weight: 600; font-size: 13px;"
        )
        layout.addWidget(moldet_row)

        # Scribe 置信度 — text_secondary
        scribe_row = InfoRow("Scribe 置信度", f"{self.detection.scribe_conf:.2f}")
        scribe_row.value_label.setStyleSheet(
            f"color: {p['text_secondary']}; font-weight: 600; font-size: 13px;"
        )
        layout.addWidget(scribe_row)

        layout.addWidget(InfoRow("状态", self.detection.status))

        # 3. 状态操作按钮
        btn_layout = QHBoxLayout()
        self.btn_confirm = BaseButton("确认")
        self.btn_reject = BaseButton("拒绝")
        self.btn_edit = BaseButton("在编辑器中打开...")
        btn_layout.addWidget(self.btn_confirm)
        btn_layout.addWidget(self.btn_reject)
        btn_layout.addWidget(self.btn_edit)
        layout.addLayout(btn_layout)

        self.btn_confirm.clicked.connect(
            lambda: self.status_changed.emit(self.detection.id, "confirmed")
        )
        self.btn_reject.clicked.connect(
            lambda: self.status_changed.emit(self.detection.id, "rejected")
        )
        self.btn_edit.clicked.connect(
            lambda: self.edit_requested.emit(self.detection.id)
        )

        # 4. 批注编辑
        layout.addWidget(QLabel("批注:"))
        self.comment_edit = QTextEdit()
        self.comment_edit.setPlainText(self.detection.comment)
        self.comment_edit.setMaximumHeight(80)
        layout.addWidget(self.comment_edit)

        self.btn_save_comment = BaseButton("保存批注")
        self.btn_save_comment.clicked.connect(self._on_save_comment)
        layout.addWidget(self.btn_save_comment)

        # 5. E-SMILES 修正结果展示/编辑
        layout.addWidget(QLabel("修正后的 E-SMILES:"))
        self.esmiles_edit = QTextEdit()
        self.esmiles_edit.setPlainText(
            self.detection.corrected_esmiles or self.detection.smiles
        )
        self.esmiles_edit.setMaximumHeight(60)
        layout.addWidget(self.esmiles_edit)

        self.btn_save_esmiles = BaseButton("保存修正")
        self.btn_save_esmiles.clicked.connect(self._on_save_esmiles)
        layout.addWidget(self.btn_save_esmiles)

    def _on_save_comment(self) -> None:
        text = self.comment_edit.toPlainText().strip()
        self.comment_saved.emit(self.detection.id, text)

    def _on_save_esmiles(self) -> None:
        esmiles = self.esmiles_edit.toPlainText().strip()
        self.esmiles_saved.emit(self.detection.id, esmiles)
        self.status_changed.emit(self.detection.id, "corrected")
