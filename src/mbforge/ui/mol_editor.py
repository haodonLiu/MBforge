"""交互式分子编辑器 — 基于 RDKit rdMolDraw2D + PyQt6."""

from __future__ import annotations

import math
from enum import Enum
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QSizePolicy, QWidget

from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.Draw import rdMolDraw2D

from ..molecules.esmiles import ESmilesTag, esmiles_to_mol, mol_to_esmiles, parse_esmiles
from .theme import ThemeManager


class EditorTool(Enum):
    """编辑器工具模式."""

    SELECT = "select"
    ADD_ATOM = "add_atom"
    ADD_BOND = "add_bond"
    DELETE = "delete"


class MolEditorWidget(QWidget):
    """交互式分子编辑器.

    支持从 E-SMILES 渲染分子、点击选中原子/键、添
    加原子/键、删除原子/键等操作。
    """

    # E-SMILES 变化时发出（带完整 E-SMILES 字符串）
    smiles_changed = pyqtSignal(str)

    # 画布大小（固定，坐标映射到 widget 缩放）
    CANVAS_SIZE = QSize(500, 500)
    HIT_RADIUS = 15  # 像素，点击容差

    def __init__(self, esmiles: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(300, 200)
        self.setMouseTracking(True)

        self._tool = EditorTool.SELECT
        self._atom_type = "C"
        self._bond_order = Chem.BondType.SINGLE
        self._selected_atom: Optional[int] = None
        self._selected_bond: Optional[int] = None
        self._pending_atom: Optional[int] = None  # ADD_BOND 第一步选中的原子
        self._highlight_atoms: set[int] = set()
        self._highlight_bonds: set[int] = set()
        self._atom_colors: dict[int, tuple] = {}
        self._mol: Optional[Chem.ROMol] = None
        self._tags: list[ESmilesTag] = []
        self._drawer: Optional[rdMolDraw2D.MolDraw2DCairo] = None
        self._pixmap: Optional[QPixmap] = None

        self._setup_ui()
        if esmiles:
            self.set_esmiles(esmiles)

    def _setup_ui(self):
        p = ThemeManager.instance().palette()
        self.setStyleSheet(f"""
            MolEditorWidget {{
                background: {p['bg_card']};
                border: 1px solid {p['border']};
                border-radius: 8px;
            }}
        """)

    # ---- Public API ----

    def set_esmiles(self, esmiles: str):
        """加载 E-SMILES 字符串到编辑器."""
        try:
            self._mol, self._tags = esmiles_to_mol(esmiles)
        except ValueError:
            # SMILES 无效，显示空白
            self._mol = None
            self._tags = []
        self._selected_atom = None
        self._selected_bond = None
        self._pending_atom = None
        self._highlight_atoms.clear()
        self._highlight_bonds.clear()
        self._atom_colors.clear()
        self._recompute_coords()
        self._render()
        self.update()

    def get_esmiles(self) -> str:
        """获取当前 E-SMILES 字符串."""
        if self._mol is None:
            return ""
        return mol_to_esmiles(self._mol, self._tags)

    def set_tool(self, tool: EditorTool):
        """切换工具模式."""
        self._tool = tool
        self._pending_atom = None
        self.update()

    def set_atom_type(self, atom: str):
        """设置要添加的原子类型."""
        self._atom_type = atom

    # ---- Internal ----

    def _recompute_coords(self):
        """重新计算 2D 坐标."""
        if self._mol is not None:
            AllChem.Compute2DCoords(self._mol)

    def _render(self):
        """将分子渲染到 _pixmap."""
        if self._mol is None:
            self._pixmap = QPixmap()
            return

        w, h = self.CANVAS_SIZE.width(), self.CANVAS_SIZE.height()
        self._drawer = rdMolDraw2D.MolDraw2DCairo(w, h)
        self._drawer.drawOptions().addAtomIndices = False
        self._drawer.drawOptions().addBondIndices = False

        hl_atoms = list(self._highlight_atoms) or None
        hl_bonds = list(self._highlight_bonds) or None

        rdMolDraw2D.PrepareAndDrawMolecule(
            self._drawer,
            self._mol,
            highlightAtoms=hl_atoms,
            highlightBonds=hl_bonds,
            highlightAtomColors=self._atom_colors,
        )
        self._drawer.FinishDrawing()

        img_bytes = self._drawer.GetDrawingText()
        qimage = QImage.fromData(img_bytes)
        self._pixmap = QPixmap.fromImage(qimage)

    def _canvas_from_event(self, event_x: float, event_y: float):
        """将 widget 坐标转换为 canvas 坐标."""
        scale_x = self.CANVAS_SIZE.width() / self.width()
        scale_y = self.CANVAS_SIZE.height() / self.height()
        return event_x * scale_x, event_y * scale_y

    def _hit_test(self, cx: float, cy: float):
        """Hit test，返回 ("atom", idx) | ("bond", idx) | None."""
        if self._mol is None:
            return None

        # 先检测键（线段距离）
        for bond_idx in range(self._mol.GetNumBonds()):
            bond = self._mol.GetBondWithIdx(bond_idx)
            a1 = bond.GetBeginAtomIdx()
            a2 = bond.GetEndAtomIdx()
            p1 = self._drawer.GetDrawCoords(a1)
            p2 = self._drawer.GetDrawCoords(a2)
            dist = self._point_to_segment_dist(cx, cy, p1.x, p1.y, p2.x, p2.y)
            if dist < self.HIT_RADIUS:
                return ("bond", bond_idx)

        # 再检测原子（点到圆心距离）
        for atom_idx in range(self._mol.GetNumAtoms()):
            pt = self._drawer.GetDrawCoords(atom_idx)
            dist = math.hypot(pt.x - cx, pt.y - cy)
            if dist < self.HIT_RADIUS * 2:
                return ("atom", atom_idx)

        return None

    @staticmethod
    def _point_to_segment_dist(px: float, py: float,
                                ax: float, ay: float,
                                bx: float, by: float) -> float:
        """点 (px,py) 到线段 (a→b) 的最短距离."""
        dx = bx - ax
        dy = by - ay
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        return math.hypot(px - proj_x, py - proj_y)

    def _atom_color(self, idx: int) -> tuple:
        """获取原子高亮色（红色 = 选中）。"""
        return (1.0, 0.3, 0.3, 1.0)

    def _highlight(self, atom_idx: Optional[int] = None,
                   bond_idx: Optional[int] = None):
        """高亮指定原子/键，清除之前高亮."""
        self._highlight_atoms.clear()
        self._highlight_bonds.clear()
        self._atom_colors.clear()
        if atom_idx is not None:
            self._highlight_atoms.add(atom_idx)
            self._atom_colors[atom_idx] = self._atom_color(atom_idx)
        if bond_idx is not None:
            self._highlight_bonds.add(bond_idx)
        self._render()
        self.update()

    # ---- Edit Operations ----

    def _op_add_atom(self, target_idx: int):
        """在 target_idx 原子上添加新原子."""
        rwmol = Chem.RWMol(self._mol)
        new_idx = rwmol.AddAtom(Chem.Atom(self._atom_type))
        rwmol.AddBond(target_idx, new_idx, order=self._bond_order)
        AllChem.Compute2DCoords(rwmol)
        self._mol = rwmol
        self._tags = self._update_tags_after_edit()
        self._highlight(new_idx)
        self._emit_changed()

    def _op_add_atom_free(self, cx: float, cy: float):
        """在空白处添加游离原子（位置参考最近原子方向）。"""
        rwmol = Chem.RWMol(self._mol)
        conf = rwmol.GetConformer(0)
        # 在点击位置附近找一个虚拟坐标（等距排列）
        x = cx / self.CANVAS_SIZE.width()
        y = 1.0 - cy / self.CANVAS_SIZE.height()  # flip y for chemistry
        new_idx = rwmol.AddAtom(Chem.Atom(self._atom_type))
        AllChem.Compute2DCoords(rwmol)
        self._mol = rwmol
        self._tags = self._update_tags_after_edit()
        self._highlight(new_idx)
        self._emit_changed()

    def _op_add_bond(self, atom_a: int, atom_b: int):
        """在 atom_a 和 atom_b 之间建立键."""
        rwmol = Chem.RWMol(self._mol)
        if not rwmol.GetBondBetweenAtoms(atom_a, atom_b):
            rwmol.AddBond(atom_a, atom_b, order=self._bond_order)
            AllChem.Compute2DCoords(rwmol)
            self._mol = rwmol
            self._tags = self._update_tags_after_edit()
            self._highlight(atom_b)
            self._emit_changed()
        else:
            self._highlight(atom_b)

    def _op_delete_atom(self, atom_idx: int):
        """删除原子及其所有键."""
        rwmol = Chem.RWMol(self._mol)
        rwmol.RemoveAtom(atom_idx)
        AllChem.Compute2DCoords(rwmol)
        self._mol = rwmol
        self._tags = self._update_tags_after_edit()
        self._selected_atom = None
        self._selected_bond = None
        self._render()
        self._emit_changed()
        self.update()

    def _op_delete_bond(self, bond_idx: int):
        """删除键（保留两端原子）。"""
        rwmol = Chem.RWMol(self._mol)
        bond = rwmol.GetBondWithIdx(bond_idx)
        a1 = bond.GetBeginAtomIdx()
        a2 = bond.GetEndAtomIdx()
        rwmol.RemoveBond(a1, a2)
        AllChem.Compute2DCoords(rwmol)
        self._mol = rwmol
        self._tags = self._update_tags_after_edit()
        self._selected_bond = None
        self._render()
        self._emit_changed()
        self.update()

    def _update_tags_after_edit(self):
        """编辑后调整 tag 索引（删除原子时后续原子索引 -1）。"""
        return self._tags  # 目前简单处理，复杂编辑后再细化

    def _emit_changed(self):
        esmiles = self.get_esmiles()
        self.smiles_changed.emit(esmiles)

    # ---- Qt Events ----

    def paintEvent(self, event):
        if self._pixmap is None or self._pixmap.isNull():
            painter = QPainter(self)
            p = ThemeManager.instance().palette()
            painter.fillRect(self.rect(), p["bg_card"])
            painter.end()
            return
        painter = QPainter(self)
        # 缩放 pixmap 到 widget 大小，保持比例居中
        scaled = self._pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._mol is None:
            return

        cx, cy = self._canvas_from_event(event.position().x(), event.position().y())
        hit = self._hit_test(cx, cy)

        if self._tool == EditorTool.SELECT:
            if hit:
                if hit[0] == "atom":
                    self._selected_atom = hit[1]
                    self._selected_bond = None
                    self._highlight(atom_idx=hit[1])
                else:
                    self._selected_bond = hit[1]
                    self._selected_atom = None
                    self._highlight(bond_idx=hit[1])
            else:
                self._selected_atom = None
                self._selected_bond = None
                self._highlight_atoms.clear()
                self._highlight_bonds.clear()
                self._atom_colors.clear()
                self._render()
                self.update()

        elif self._tool == EditorTool.ADD_ATOM:
            if hit and hit[0] == "atom":
                self._op_add_atom(hit[1])
            else:
                self._op_add_atom_free(cx, cy)

        elif self._tool == EditorTool.ADD_BOND:
            if hit and hit[0] == "atom":
                if self._pending_atom is None:
                    self._pending_atom = hit[1]
                    self._highlight(atom_idx=hit[1])
                else:
                    self._op_add_bond(self._pending_atom, hit[1])
                    self._pending_atom = None

        elif self._tool == EditorTool.DELETE:
            if hit:
                if hit[0] == "atom":
                    self._op_delete_atom(hit[1])
                else:
                    self._op_delete_bond(hit[1])

    def enterEvent(self, event):
        self.setCursor(Qt.CursorShape.PointingHandCursor)
