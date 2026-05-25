"""交互式分子编辑器 — 基于 QGraphicsScene + RDKit 双层架构.

架构：
- 数据层：RDKit Mol（RWMol 骨架）+ ESmilesTag（扩展标签）
- 渲染层：MolEditorScene（QGraphicsView + QGraphicsScene，Scene坐标=RDKit 2D坐标）
- 交互层：MolEditorWidget（工具状态机 + 编辑操作 + Undo/Redo）
"""

from __future__ import annotations


from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from rdkit import Chem
from rdkit.Chem import AllChem

from ...molecules.esmiles import ESmilesTag, esmiles_to_mol, mol_to_esmiles
from .items import (
    AtomItem,
    BondItem,
    EditorTool,
    MolEditorScene,
)


class MolEditorWidget(QWidget):
    """交互式分子编辑器 — 工具状态机 + 编辑操作 + Undo/Redo."""

    smiles_changed = pyqtSignal(str)

    def __init__(self, esmiles: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)

        self._tool = EditorTool.SELECT
        self._atom_type = "C"
        self._bond_order = Chem.BondType.SINGLE
        self._selected_atom: int | None = None
        self._selected_bond: int | None = None
        self._pending_atom: int | None = None
        self._mol: Chem.ROMol | None = None
        self._tags: list[ESmilesTag] = []
        self._atom_items: dict[int, AtomItem] = {}
        self._bond_items: dict[int, BondItem] = {}
        self._tag_items: list = []

        # Undo/Redo
        self._history: list[tuple[Chem.Mol, list[ESmilesTag]]] = []
        self._history_pos: int = -1
        self._max_history: int = 50

        # Debounce
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._on_debounce_timeout)
        self._pending_esmiles: str = ""

        # Scene + View
        self._scene = MolEditorScene(self)
        self._scene.smiles_changed.connect(self._on_scene_smiles_changed)
        self._scene.atom_clicked.connect(self._on_atom_clicked)
        self._scene.bond_clicked.connect(self._on_bond_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._scene)

        if esmiles:
            self.set_esmiles(esmiles)

    # ---- Public API ----

    def set_esmiles(self, esmiles: str):
        try:
            self._mol, self._tags = esmiles_to_mol(esmiles)
        except ValueError:
            self._mol = None
            self._tags = []
        self._selected_atom = None
        self._selected_bond = None
        self._pending_atom = None
        self._history.clear()
        self._history_pos = -1
        self._refresh_scene()

    def get_esmiles(self) -> str:
        if self._mol is None:
            return ""
        return mol_to_esmiles(self._mol, self._tags)

    def set_tool(self, tool: EditorTool):
        self._tool = tool
        self._pending_atom = None
        self._scene.set_tool(tool)

    def set_atom_type(self, atom: str):
        self._atom_type = atom

    def set_bond_order(self, order: Chem.BondType):
        self._bond_order = order

    # ---- Scene Refresh ----

    def _refresh_scene(self):
        """根据当前 _mol 和 _tags 重建 Scene."""
        esmiles = self.get_esmiles()
        self._scene.set_esmiles(esmiles, fit_view=False)
        self._atom_items = self._scene._atom_items
        self._bond_items = self._scene._bond_items
        self._tag_items = self._scene._tag_items

    # ---- Signal Handlers ----

    def _on_scene_smiles_changed(self, esmiles: str):
        self._pending_esmiles = esmiles
        if self._debounce_timer.isActive():
            self._debounce_timer.stop()
        self._debounce_timer.start()

    def _on_debounce_timeout(self):
        self.smiles_changed.emit(self._pending_esmiles)

    def _on_atom_clicked(self, atom_idx: int):
        """处理 Scene 传来的原子点击事件 — 工具状态机."""
        if self._mol is None:
            return

        if self._tool == EditorTool.SELECT:
            self._selected_atom = atom_idx
            self._selected_bond = None
            self._highlight_selection()

        elif self._tool == EditorTool.ADD_ATOM:
            self._save_snapshot()
            self._op_add_atom(atom_idx)

        elif self._tool == EditorTool.ADD_BOND:
            if self._pending_atom is None:
                self._pending_atom = atom_idx
                # 高亮 pending 原子
                if atom_idx in self._atom_items:
                    self._atom_items[atom_idx].set_selected(True)
            else:
                # 建键
                self._save_snapshot()
                self._op_add_bond(self._pending_atom, atom_idx)
                if self._pending_atom in self._atom_items:
                    self._atom_items[self._pending_atom].set_selected(False)
                self._pending_atom = None

        elif self._tool == EditorTool.DELETE:
            self._save_snapshot()
            self._op_delete_atom(atom_idx)

    def _on_bond_clicked(self, bond_idx: int):
        """处理 Scene 传来的键点击事件 — 工具状态机."""
        if self._mol is None:
            return

        if self._tool == EditorTool.SELECT:
            self._selected_bond = bond_idx
            self._selected_atom = None
            self._highlight_selection()

        elif self._tool == EditorTool.DELETE:
            self._save_snapshot()
            self._op_delete_bond(bond_idx)

    def _highlight_selection(self):
        for idx, item in self._atom_items.items():
            item.set_selected(idx == self._selected_atom)
        for idx, item in self._bond_items.items():
            item.set_selected(idx == self._selected_bond)

    # ---- Edit Operations ----

    def _save_snapshot(self):
        if self._mol is None:
            return
        mol_copy = Chem.Mol(self._mol)
        tags_copy = [ESmilesTag(type=t.type, index=t.index, group=t.group) for t in self._tags]
        self._history = self._history[:self._history_pos + 1]
        self._history.append((mol_copy, tags_copy))
        if len(self._history) > self._max_history:
            self._history.pop(0)
        else:
            self._history_pos += 1

    def undo(self):
        if self._history_pos <= 0:
            return
        self._history_pos -= 1
        mol, tags = self._history[self._history_pos]
        self._mol = mol
        self._tags = [ESmilesTag(type=t.type, index=t.index, group=t.group) for t in tags]
        self._selected_atom = None
        self._selected_bond = None
        self._pending_atom = None
        self._refresh_scene()
        self._emit_changed()

    def redo(self):
        if self._history_pos >= len(self._history) - 1:
            return
        self._history_pos += 1
        mol, tags = self._history[self._history_pos]
        self._mol = mol
        self._tags = [ESmilesTag(type=t.type, index=t.index, group=t.group) for t in tags]
        self._selected_atom = None
        self._selected_bond = None
        self._pending_atom = None
        self._refresh_scene()
        self._emit_changed()

    def _op_add_atom(self, target_idx: int):
        rwmol = Chem.RWMol(self._mol)
        new_idx = rwmol.AddAtom(Chem.Atom(self._atom_type))
        rwmol.AddBond(target_idx, new_idx, order=self._bond_order)
        AllChem.Compute2DCoords(rwmol)
        self._mol = rwmol
        self._tags = self._update_tags_after_edit()
        self._refresh_scene()
        self._emit_changed()

    def _op_add_atom_free(self, cx: float, cy: float):
        rwmol = Chem.RWMol(self._mol)
        rwmol.AddAtom(Chem.Atom(self._atom_type))
        AllChem.Compute2DCoords(rwmol)
        self._mol = rwmol
        self._tags = self._update_tags_after_edit()
        self._refresh_scene()
        self._emit_changed()

    def _op_add_bond(self, atom_a: int, atom_b: int):
        rwmol = Chem.RWMol(self._mol)
        if not rwmol.GetBondBetweenAtoms(atom_a, atom_b):
            rwmol.AddBond(atom_a, atom_b, order=self._bond_order)
            AllChem.Compute2DCoords(rwmol)
            self._mol = rwmol
            self._tags = self._update_tags_after_edit()
            self._refresh_scene()
            self._emit_changed()

    def _op_delete_atom(self, atom_idx: int):
        rwmol = Chem.RWMol(self._mol)
        rwmol.RemoveAtom(atom_idx)
        AllChem.Compute2DCoords(rwmol)
        self._mol = rwmol
        self._tags = self._update_tags_after_edit(deleted_atom_idx=atom_idx)
        self._selected_atom = None
        self._selected_bond = None
        self._refresh_scene()
        self._emit_changed()

    def _op_delete_bond(self, bond_idx: int):
        rwmol = Chem.RWMol(self._mol)
        bond = rwmol.GetBondWithIdx(bond_idx)
        rwmol.RemoveBond(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())
        AllChem.Compute2DCoords(rwmol)
        self._mol = rwmol
        self._tags = self._update_tags_after_edit()
        self._selected_bond = None
        self._refresh_scene()
        self._emit_changed()

    def _update_tags_after_edit(self, deleted_atom_idx: int | None = None):
        if deleted_atom_idx is None:
            new_tags: list[ESmilesTag] = []
            for tag in self._tags:
                if tag.type == "a" and tag.index >= self._mol.GetNumAtoms():
                    continue
                new_tags.append(tag)
            return new_tags

        new_tags: list[ESmilesTag] = []
        for tag in self._tags:
            if tag.type == "a":
                if tag.index == deleted_atom_idx:
                    continue
                if tag.index > deleted_atom_idx:
                    new_tags.append(ESmilesTag(type=tag.type, index=tag.index - 1, group=tag.group))
                else:
                    new_tags.append(tag)
            else:
                new_tags.append(tag)
        return new_tags

    def _emit_changed(self):
        if self._debounce_timer.isActive():
            self._debounce_timer.stop()
        self._pending_esmiles = self.get_esmiles()
        self._debounce_timer.start()

    # ---- Keyboard ----

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_Z:
                self.undo()
                return
            if event.key() == Qt.Key.Key_Y:
                self.redo()
                return
        super().keyPressEvent(event)
