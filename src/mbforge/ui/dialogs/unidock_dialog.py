"""UniDock 对接配置对话框."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .theme import ThemeManager, create_input


class UniDockConfigDialog(QDialog):
    """UniDock 分子对接配置对话框."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("UniDock 对接配置")
        self.setMinimumWidth(550)
        ThemeManager.apply_dialog(self)
        self._setup_ui()

    def _setup_ui(self):
        """构建对话框 UI."""
        layout = QVBoxLayout(self)

        # 表单布局
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setSpacing(10)

        # ---- 受体文件 ----
        receptor_layout = QHBoxLayout()
        self.receptor_edit = create_input(placeholder="选择受体蛋白 PDBQT 文件")
        self.receptor_edit.setToolTip("受体蛋白 PDBQT 文件路径")
        self.browse_receptor_btn = QPushButton("浏览...")
        self.browse_receptor_btn.clicked.connect(self._browse_receptor)
        receptor_layout.addWidget(self.receptor_edit)
        receptor_layout.addWidget(self.browse_receptor_btn)
        form.addRow("受体文件:", receptor_layout)

        # ---- 配体 SMILES ----
        self.ligand_edit = create_input(placeholder="输入配体分子 SMILES，如 CC(=O)Oc1ccccc1C(=O)O")
        self.ligand_edit.setToolTip("配体分子 SMILES 字符串，如 CC(=O)Oc1ccccc1C(=O)O")
        form.addRow("配体 SMILES:", self.ligand_edit)

        # ---- 对接盒子中心 ----
        center_group = QWidget()
        center_layout = QHBoxLayout(center_group)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(8)

        self.center_x = QDoubleSpinBox()
        self.center_x.setRange(-9999.0, 9999.0)
        self.center_x.setDecimals(3)
        self.center_x.setValue(0.0)
        self.center_x.setToolTip("对接盒子中心 X 坐标（Å）")
        self.center_x.setPrefix("X: ")
        center_layout.addWidget(self.center_x)

        self.center_y = QDoubleSpinBox()
        self.center_y.setRange(-9999.0, 9999.0)
        self.center_y.setDecimals(3)
        self.center_y.setValue(0.0)
        self.center_y.setToolTip("对接盒子中心 Y 坐标（Å）")
        self.center_y.setPrefix("Y: ")
        center_layout.addWidget(self.center_y)

        self.center_z = QDoubleSpinBox()
        self.center_z.setRange(-9999.0, 9999.0)
        self.center_z.setDecimals(3)
        self.center_z.setValue(0.0)
        self.center_z.setToolTip("对接盒子中心 Z 坐标（Å）")
        self.center_z.setPrefix("Z: ")
        center_layout.addWidget(self.center_z)

        form.addRow("盒子中心:", center_group)

        # ---- 对接盒子尺寸 ----
        size_group = QWidget()
        size_layout = QHBoxLayout(size_group)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.setSpacing(8)

        self.size_x = QDoubleSpinBox()
        self.size_x.setRange(1.0, 9999.0)
        self.size_x.setDecimals(1)
        self.size_x.setValue(22.5)
        self.size_x.setToolTip("对接盒子 X 方向尺寸（Å）")
        self.size_x.setPrefix("X: ")
        size_layout.addWidget(self.size_x)

        self.size_y = QDoubleSpinBox()
        self.size_y.setRange(1.0, 9999.0)
        self.size_y.setDecimals(1)
        self.size_y.setValue(22.5)
        self.size_y.setToolTip("对接盒子 Y 方向尺寸（Å）")
        self.size_y.setPrefix("Y: ")
        size_layout.addWidget(self.size_y)

        self.size_z = QDoubleSpinBox()
        self.size_z.setRange(1.0, 9999.0)
        self.size_z.setDecimals(1)
        self.size_z.setValue(22.5)
        self.size_z.setToolTip("对接盒子 Z 方向尺寸（Å）")
        self.size_z.setPrefix("Z: ")
        size_layout.addWidget(self.size_z)

        form.addRow("盒子尺寸:", size_group)

        # ---- 搜索模式 ----
        self.search_mode = QComboBox()
        self.search_mode.addItems(["fast", "balance", "detail"])
        self.search_mode.setCurrentText("balance")
        self.search_mode.setToolTip(
            "fast：最快（适合大规模初筛）\nbalance：平衡，推荐默认\ndetail：最精确（适合精筛）"
        )
        form.addRow("搜索模式:", self.search_mode)

        # ---- 打分函数 ----
        self.scoring = QComboBox()
        self.scoring.addItems(["vina", "vinardo", "ad4"])
        self.scoring.setCurrentText("vina")
        self.scoring.setToolTip(
            "vina：AutoDock Vina 打分函数\nvinardo：更快\nad4：AutoDock4 打分函数"
        )
        form.addRow("打分函数:", self.scoring)

        # ---- 输出构象数量 ----
        self.num_modes = QSpinBox()
        self.num_modes.setRange(1, 100)
        self.num_modes.setValue(9)
        self.num_modes.setToolTip("最多输出多少个结合构象")
        form.addRow("输出构象数:", self.num_modes)

        # ---- 搜索穷尽度 ----
        self.exhaustiveness = QSpinBox()
        self.exhaustiveness.setRange(1, 256)
        self.exhaustiveness.setValue(32)
        self.exhaustiveness.setToolTip("搜索穷尽度，数值越大越慢但越精确")
        form.addRow("穷尽度:", self.exhaustiveness)

        layout.addLayout(form)

        # ---- 按钮 ----
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_receptor(self):
        """打开受体文件选择对话框."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择受体蛋白 PDBQT 文件",
            "",
            "PDBQT 文件 (*.pdbqt);;所有文件 (*)",
        )
        if path:
            self.receptor_edit.setText(path)

    def _on_ok(self):
        """点击确定按钮时的验证逻辑."""
        receptor = self.receptor_edit.text().strip()
        ligand = self.ligand_edit.text().strip()

        if not receptor:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "验证失败", "请选择受体蛋白文件")
            return
        if not ligand:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "验证失败", "请输入配体分子 SMILES")
            return

        self.accept()

    def get_config(self) -> dict:
        """获取当前配置参数.

        Returns:
            包含所有对接参数的字典
        """
        return {
            "receptor_file": self.receptor_edit.text().strip(),
            "ligand_smiles": self.ligand_edit.text().strip(),
            "center_x": self.center_x.value(),
            "center_y": self.center_y.value(),
            "center_z": self.center_z.value(),
            "size_x": self.size_x.value(),
            "size_y": self.size_y.value(),
            "size_z": self.size_z.value(),
            "search_mode": self.search_mode.currentText(),
            "scoring": self.scoring.currentText(),
            "num_modes": self.num_modes.value(),
            "exhaustiveness": self.exhaustiveness.value(),
        }
