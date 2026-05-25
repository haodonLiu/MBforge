"""分子编辑器 Dock — 集成工具栏 + 预设片段 + MolEditorWidget."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..molecules.presets import PRESETS
from .mol_editor import EditorTool, MolEditorWidget
from .theme import CardWidget, ThemeManager, create_button


class MolEditorDock(QDockWidget):
    """分子编辑器 Dock，集成工具栏 + 预设片段 + 编辑器主件."""

    # 当编辑器中分子变化时发出（E-SMILES 字符串）
    molecule_changed = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("分子编辑器", parent)
        self.setObjectName("MolEditorDock")
        self._setup_ui()

        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _setup_ui(self):
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # SMILES 输入框
        input_card = CardWidget("")
        input_layout = QVBoxLayout()
        self._smiles_input = QLineEdit()
        self._smiles_input.setPlaceholderText("输入 SMILES 或 E-SMILES，回车加载")
        self._smiles_input.returnPressed.connect(self._on_load_smiles)
        input_layout.addWidget(self._smiles_input)
        input_card.add_layout(input_layout)
        layout.addWidget(input_card)

        # 编辑器工具栏
        toolbar_card = CardWidget("工具")
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(6)

        self._tool_buttons: dict[EditorTool, QWidget] = {}
        self._tool_group = []
        for tool in EditorTool:
            btn = create_button(tool.value, style="default")
            btn.setCheckable(True)
            btn.setMaximumWidth(80)
            btn.clicked.connect(lambda checked, t=tool: self._on_tool_changed(t))
            toolbar_layout.addWidget(btn)
            self._tool_buttons[tool] = btn
            self._tool_group.append((btn, tool))

        # 默认选中 SELECT
        self._tool_buttons[EditorTool.SELECT].setChecked(True)

        toolbar_layout.addStretch()
        toolbar_card.add_layout(toolbar_layout)
        layout.addWidget(toolbar_card)

        # 原子类型选择
        atom_card = CardWidget("原子类型")
        atom_layout = QHBoxLayout()
        atom_layout.setSpacing(4)
        self._atom_buttons: dict[str, QWidget] = {}
        for atom in ["C", "N", "O", "S", "P", "F", "Cl", "Br"]:
            btn = create_button(atom, style="default")
            btn.setCheckable(True)
            btn.setMaximumWidth(40)
            btn.clicked.connect(lambda checked, a=atom: self._on_atom_changed(a))
            atom_layout.addWidget(btn)
            self._atom_buttons[atom] = btn

        # 默认 C
        self._atom_buttons["C"].setChecked(True)
        atom_layout.addStretch()
        atom_card.add_layout(atom_layout)
        layout.addWidget(atom_card)

        # 预设片段
        preset_card = CardWidget("预设片段")
        preset_layout = QVBoxLayout()
        self._preset_list = QListWidget()
        self._preset_list.setSpacing(2)
        self._preset_list.itemClicked.connect(self._on_preset_clicked)
        for p in PRESETS:
            item = QListWidgetItem(p["name"])
            item.setData(Qt.ItemDataRole.UserRole, p["esmiles"])
            item.setToolTip(p["esmiles"])
            self._preset_list.addItem(item)
        preset_layout.addWidget(self._preset_list)
        preset_card.add_layout(preset_layout)
        layout.addWidget(preset_card)

        # 分子编辑器主件
        self.editor = MolEditorWidget()
        self.editor.smiles_changed.connect(self._on_editor_changed)
        layout.addWidget(self.editor, 1)

        # 输出 E-SMILES（只读）
        self._output_label = QLabel()
        self._output_label.setWordWrap(True)
        self._output_label.setStyleSheet(f"""
            QLabel {{
                font-family: monospace;
                font-size: 11px;
                color: {ThemeManager.instance().palette()['text_secondary']};
                background: {ThemeManager.instance().palette()['bg_hover']};
                padding: 4px 8px;
                border-radius: 4px;
            }}
        """)
        layout.addWidget(self._output_label)

        self.setWidget(widget)
        self._on_theme_changed(ThemeManager.instance().mode())

    def _on_theme_changed(self, mode: str):
        """Theme 切换时刷新样式."""
        self._smiles_input.setStyleSheet("")
        self._output_label.setStyleSheet(f"""
            QLabel {{
                font-family: monospace;
                font-size: 11px;
                color: {ThemeManager.instance().palette()['text_secondary']};
                background: {ThemeManager.instance().palette()['bg_hover']};
                padding: 4px 8px;
                border-radius: 4px;
            }}
        """)

    def _on_load_smiles(self):
        esmiles = self._smiles_input.text().strip()
        if esmiles:
            self.editor.set_esmiles(esmiles)
            self._output_label.setText(esmiles)

    def _on_tool_changed(self, tool: EditorTool):
        for t, btn in self._tool_buttons.items():
            btn.setChecked(t == tool)
        self.editor.set_tool(tool)

    def _on_atom_changed(self, atom: str):
        for a, btn in self._atom_buttons.items():
            btn.setChecked(a == atom)
        self.editor.set_atom_type(atom)

    def _on_preset_clicked(self, item: QListWidgetItem):
        esmiles = item.data(Qt.ItemDataRole.UserRole)
        self._smiles_input.setText(esmiles)
        self.editor.set_esmiles(esmiles)
        self._output_label.setText(esmiles)

    def _on_editor_changed(self, esmiles: str):
        self._output_label.setText(esmiles)
        self.molecule_changed.emit(esmiles)

    def set_esmiles(self, esmiles: str):
        """外部设置 E-SMILES（如从 PDF 识别结果加载）。"""
        self._smiles_input.setText(esmiles)
        self.editor.set_esmiles(esmiles)
        self._output_label.setText(esmiles)
