"""分子编辑器 Dock — 集成工具栏 + 预设片段 + MolEditorWidget."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDockWidget,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from ..molecules.presets import PRESETS
from .mol_editor import EditorTool, MolEditorWidget
from .theme import CardWidget, ThemeManager, create_button


class _ShortcutsPanel(QFrame):
    """可折叠的快捷键面板，显示所有预设片段（按类别分组）."""

    preset_selected = pyqtSignal(QListWidgetItem)

    # 类别定义
    CATEGORIES = [
        ("环", ["苯环", "环己烷", "环戊烷", "吡啶", "噻唑", "呋喃", "哌啶", "吡咯", "吲哚"]),
        ("官能团", ["羧基", "氨基", "甲基", "羟基", "酰胺", "磺酰基", "酯基", "酮基", "醛基", "氰基", "硝基"]),
        ("卤素", ["氟", "氯", "溴", "碘"]),
        ("Markush", ["R[1] 连接点", "R[1] 苯环", "R[1] 羧基", "R[1]+R[2] 苯环"]),
    ]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._expanded = True
        self._setup_ui()
        self._on_toggle()

    def _setup_ui(self):
        p = ThemeManager.instance().palette()

        self.setStyleSheet(f"""
            QFrame {{
                background: {p['bg_card']};
                border: 1px solid {p['border']};
                border-radius: 6px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 标题栏（可点击展开/折叠）
        header = QHBoxLayout()
        self._toggle_btn = create_button("▾ 快捷键", style="default")
        self._toggle_btn.setStyleSheet("border: none; background: transparent; padding: 2px 4px;")
        self._toggle_btn.clicked.connect(self._on_toggle)
        header.addWidget(self._toggle_btn)
        header.addStretch()
        layout.addLayout(header)

        # 内容区（滚动）
        self._content = QScrollArea()
        self._content.setWidgetResizable(True)
        self._content.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content.setMaximumHeight(180)
        self._content.setMinimumHeight(0)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(8)
        content_layout.setContentsMargins(4, 4, 4, 4)

        for cat_name, items in self.CATEGORIES:
            cat_label = QLabel(cat_name)
            cat_label.setStyleSheet(f"color: {p['brand_primary']}; font-weight: 600; font-size: 11px;")
            content_layout.addWidget(cat_label)

            grid = QGridLayout()
            grid.setSpacing(3)
            col = 0
            row = 0
            for item_name in items:
                btn = create_button(item_name, style="default")
                btn.setStyleSheet("padding: 3px 6px; font-size: 11px;")
                # Find preset by name and store esmiles
                esmiles = self._find_preset(item_name)
                if esmiles:
                    btn.clicked.connect(lambda checked, e=esmiles, n=item_name: self._on_preset(n, e))
                btn.setToolTip(esmiles if esmiles else "")
                grid.addWidget(btn, row, col)
                col += 1
                if col >= 4:
                    col = 0
                    row += 1
            content_layout.addLayout(grid)

        self._content.setWidget(content_widget)
        layout.addWidget(self._content)

    def _find_preset(self, name: str) -> str:
        for p in PRESETS:
            if p["name"] == name:
                return p["esmiles"]
        return ""

    def _on_preset(self, name: str, esmiles: str):
        item = QListWidgetItem(name)
        item.setData(Qt.ItemDataRole.UserRole, esmiles)
        self.preset_selected.emit(item)

    def _on_toggle(self):
        self._expanded = not self._expanded
        self._toggle_btn.setText("▾ 快捷键" if self._expanded else "▸ 快捷键")
        self._content.setMaximumHeight(180 if self._expanded else 0)
        self._content.setMinimumHeight(0 if self._expanded else 0)


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

        # 键类型选择
        bond_card = CardWidget("键类型")
        bond_layout = QHBoxLayout()
        bond_layout.setSpacing(4)
        self._bond_buttons: dict[str, QWidget] = {}
        for bond in ["SINGLE", "DOUBLE", "TRIPLE", "AROMATIC"]:
            btn = create_button(bond, style="default")
            btn.setCheckable(True)
            btn.setMaximumWidth(70)
            btn.clicked.connect(lambda checked, b=bond: self._on_bond_changed(b))
            bond_layout.addWidget(btn)
            self._bond_buttons[bond] = btn

        # 默认 SINGLE
        self._bond_buttons["SINGLE"].setChecked(True)
        bond_layout.addStretch()
        bond_card.add_layout(bond_layout)
        layout.addWidget(bond_card)

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

        # 快捷键面板（可折叠）
        self._shortcuts_panel = _ShortcutsPanel(self)
        self._shortcuts_panel.preset_selected.connect(self._on_preset_clicked)
        layout.addWidget(self._shortcuts_panel)

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

        # 实时分子式显示
        self._formula_label = QLabel()
        self._formula_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._formula_label.setStyleSheet(f"""
            QLabel {{
                font-size: 13px;
                font-weight: 600;
                color: {ThemeManager.instance().palette()['text_secondary']};
                padding: 2px 8px;
            }}
        """)
        layout.addWidget(self._formula_label)

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
        self._formula_label.setStyleSheet(f"""
            QLabel {{
                font-size: 13px;
                font-weight: 600;
                color: {ThemeManager.instance().palette()['text_secondary']};
                padding: 2px 8px;
            }}
        """)

    def _on_load_smiles(self):
        esmiles = self._smiles_input.text().strip()
        if esmiles:
            self.editor.set_esmiles(esmiles)
            self._output_label.setText(esmiles)
            self._update_formula(esmiles)

    def _on_tool_changed(self, tool: EditorTool):
        for t, btn in self._tool_buttons.items():
            btn.setChecked(t == tool)
        self.editor.set_tool(tool)

    def _on_atom_changed(self, atom: str):
        for a, btn in self._atom_buttons.items():
            btn.setChecked(a == atom)
        self.editor.set_atom_type(atom)

    def _on_bond_changed(self, bond: str):
        for b, btn in self._bond_buttons.items():
            btn.setChecked(b == bond)
        order_map = {
            "SINGLE": Chem.BondType.SINGLE,
            "DOUBLE": Chem.BondType.DOUBLE,
            "TRIPLE": Chem.BondType.TRIPLE,
            "AROMATIC": Chem.BondType.AROMATIC,
        }
        self.editor.set_bond_order(order_map[bond])

    def _on_preset_clicked(self, item: QListWidgetItem):
        esmiles = item.data(Qt.ItemDataRole.UserRole)
        self._smiles_input.setText(esmiles)
        self.editor.set_esmiles(esmiles)
        self._output_label.setText(esmiles)

    def _on_editor_changed(self, esmiles: str):
        self._output_label.setText(esmiles)
        self._update_formula(esmiles)
        self.molecule_changed.emit(esmiles)

    def _update_formula(self, esmiles: str):
        """计算并更新分子式标签."""
        try:
            smiles_part = esmiles.split("<sep>")[0]
            mol = Chem.MolFromSmiles(smiles_part)
            if mol is None:
                self._formula_label.setText("")
                return
            Chem.SanitizeMol(mol)
            formula = rdMolDescriptors.CalcMolFormula(mol)
            self._formula_label.setText(formula)
        except Exception:
            self._formula_label.setText("")

    def set_esmiles(self, esmiles: str):
        """外部设置 E-SMILES（如从 PDF 识别结果加载）。"""
        self._smiles_input.setText(esmiles)
        self.editor.set_esmiles(esmiles)
        self._output_label.setText(esmiles)
