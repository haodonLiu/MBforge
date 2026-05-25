"""检测框点击弹出面板 — 分子详情 / 编辑 / 批注."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
)

from .annotations import DetectionBox
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
        info_text = (
            f"SMILES: {self.detection.smiles}\n"
            f"MolDet 置信度: {self.detection.moldet_conf:.2f}\n"
            f"Scribe 置信度: {self.detection.scribe_conf:.2f}\n"
            f"状态: {self.detection.status}"
        )
        self.info_label = QLabel(info_text)
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        # 3. 状态操作按钮
        btn_layout = QHBoxLayout()
        self.btn_confirm = QPushButton("确认")
        self.btn_reject = QPushButton("拒绝")
        self.btn_edit = QPushButton("在编辑器中打开...")
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

        self.btn_save_comment = QPushButton("保存批注")
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

        self.btn_save_esmiles = QPushButton("保存修正")
        self.btn_save_esmiles.clicked.connect(self._on_save_esmiles)
        layout.addWidget(self.btn_save_esmiles)

    def _on_save_comment(self) -> None:
        text = self.comment_edit.toPlainText().strip()
        self.comment_saved.emit(self.detection.id, text)

    def _on_save_esmiles(self) -> None:
        esmiles = self.esmiles_edit.toPlainText().strip()
        self.esmiles_saved.emit(self.detection.id, esmiles)
        self.status_changed.emit(self.detection.id, "corrected")
