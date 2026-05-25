"""交互式分子编辑器 — 基于 RDKit rdMolDraw2D + PyQt6.

三层架构：
- 数据层：RDKit Mol（骨架）+ ESmilesTag（扩展标签）
- 逻辑层：坐标映射、hit test、编辑操作
- 表现层：双层渲染（Layer 0 RDKit 骨架 + Layer 1 扩展标签叠加）
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QSizePolicy, QWidget

from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.Draw import rdMolDraw2D

from ..molecules.esmiles import ESmilesTag, esmiles_to_mol, mol_to_esmiles
from .theme import ThemeManager


class EditorTool(Enum):
    """编辑器工具模式."""

    SELECT = "select"
    ADD_ATOM = "add_atom"
    ADD_BOND = "add_bond"
    DELETE = "delete"


# ---- Transform 坐标变换 ----


class CanvasTransform:
    """双向坐标变换：canvas(500x500) ↔ widget 坐标."""

    def __init__(self):
        self.scale: float = 1.0
        self.offset_x: float = 0.0
        self.offset_y: float = 0.0
        self.scaled_w: int = 0
        self.scaled_h: int = 0

    def update(self, canvas_w: int, canvas_h: int, widget_w: int, widget_h: int):
        """根据 widget 尺寸和 canvas 尺寸更新变换参数."""
        # 保持宽高比缩放，取最小缩放比
        scale_x = widget_w / canvas_w
        scale_y = widget_h / canvas_h
        self.scale = min(scale_x, scale_y)
        self.scaled_w = int(canvas_w * self.scale)
        self.scaled_h = int(canvas_h * self.scale)
        self.offset_x = (widget_w - self.scaled_w) / 2.0
        self.offset_y = (widget_h - self.scaled_h) / 2.0

    def canvas_to_widget(self, cx: float, cy: float) -> tuple[float, float]:
        """Canvas 坐标 → Widget 坐标（用于叠加层绘制）."""
        return self.offset_x + cx * self.scale, self.offset_y + cy * self.scale

    def widget_to_canvas(self, wx: float, wy: float) -> tuple[float, float]:
        """Widget 坐标 → Canvas 坐标（用于 hit test）。"""
        return (wx - self.offset_x) / self.scale, (wy - self.offset_y) / self.scale


# ---- 颜色编码 ----

_TAG_COLORS = {
    "R[1]": (220, 50, 50, 200),   # 红底白字
    "R[2]": (50, 100, 220, 200),  # 蓝底白字
    "R[3]": (50, 180, 80, 200),   # 绿底白字
    "R[4]": (180, 80, 200, 200),  # 紫底白字
    "R[5]": (220, 140, 30, 200),  # 橙底白字
    "X": (120, 120, 120, 200),     # 灰底黑字
    "Y": (120, 120, 120, 200),
    "Z": (120, 120, 120, 200),
}


def _tag_bg_color(tag: ESmilesTag) -> QColor:
    """根据 tag 内容返回背景色."""
    group = tag.group
    if group in _TAG_COLORS:
        r, g, b, a = _TAG_COLORS[group]
        return QColor(r, g, b, a)
    # 普通缩写基团：黄底
    return QColor(240, 220, 80, 200)


# ---- 主编辑器 Widget ----


class MolEditorWidget(QWidget):
    """交互式分子编辑器（双层渲染：骨架 + 扩展标签叠加层）."""

    smiles_changed = pyqtSignal(str)

    CANVAS_SIZE = QSize(500, 500)
    HIT_RADIUS_CANVAS = 15  # canvas 坐标系中的命中半径

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
        self._pending_atom: Optional[int] = None
        self._highlight_atoms: set[int] = set()
        self._highlight_bonds: set[int] = set()
        self._atom_colors: dict[int, tuple] = {}
        self._mol: Optional[Chem.ROMol] = None
        self._tags: list[ESmilesTag] = []
        self._drawer: Optional[rdMolDraw2D.MolDraw2DCairo] = None
        self._pixmap: Optional[QPixmap] = None
        self._transform = CanvasTransform()

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
        self._tool = tool
        self._pending_atom = None
        self.update()

    def set_atom_type(self, atom: str):
        self._atom_type = atom

    # ---- 内部方法 ----

    def _recompute_coords(self):
        if self._mol is not None:
            AllChem.Compute2DCoords(self._mol)

    def _render(self):
        """将分子渲染到 _pixmap，并更新 _transform."""
        if self._mol is None:
            self._pixmap = QPixmap()
            self._update_transform()
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
        self._update_transform()

    def _update_transform(self):
        """根据当前 widget 尺寸更新坐标变换参数."""
        cw = self.CANVAS_SIZE.width()
        ch = self.CANVAS_SIZE.height()
        self._transform.update(cw, ch, self.width(), self.height())

    def _canvas_to_widget(self, cx: float, cy: float) -> tuple[float, float]:
        return self._transform.canvas_to_widget(cx, cy)

    def _widget_to_canvas(self, wx: float, wy: float) -> tuple[float, float]:
        return self._transform.widget_to_canvas(wx, wy)

    # ---- Hit Test（统一在 canvas 坐标系中判断） ----

    def _hit_test(self, cx: float, cy: float):
        """Hit test，返回 ("atom", idx) | ("bond", idx) | None."""
        if self._mol is None:
            return None

        # 键检测（线段距离）
        for bond_idx in range(self._mol.GetNumBonds()):
            bond = self._mol.GetBondWithIdx(bond_idx)
            a1 = bond.GetBeginAtomIdx()
            a2 = bond.GetEndAtomIdx()
            p1 = self._drawer.GetDrawCoords(a1)
            p2 = self._drawer.GetDrawCoords(a2)
            dist = self._point_to_segment_dist(
                cx, cy, p1.x, p1.y, p2.x, p2.y
            )
            if dist < self.HIT_RADIUS_CANVAS:
                return ("bond", bond_idx)

        # 原子检测（半径略大）
        for atom_idx in range(self._mol.GetNumAtoms()):
            pt = self._drawer.GetDrawCoords(atom_idx)
            dist = math.hypot(pt.x - cx, pt.y - cy)
            if dist < self.HIT_RADIUS_CANVAS * 1.8:
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

    def _highlight(self, atom_idx: Optional[int] = None,
                   bond_idx: Optional[int] = None):
        self._highlight_atoms.clear()
        self._highlight_bonds.clear()
        self._atom_colors.clear()
        if atom_idx is not None:
            self._highlight_atoms.add(atom_idx)
            self._atom_colors[atom_idx] = (1.0, 0.3, 0.3, 1.0)
        if bond_idx is not None:
            self._highlight_bonds.add(bond_idx)
        self._render()
        self.update()

    # ---- 编辑操作 ----

    def _op_add_atom(self, target_idx: int):
        rwmol = Chem.RWMol(self._mol)
        new_idx = rwmol.AddAtom(Chem.Atom(self._atom_type))
        rwmol.AddBond(target_idx, new_idx, order=self._bond_order)
        AllChem.Compute2DCoords(rwmol)
        self._mol = rwmol
        self._tags = self._update_tags_after_edit()
        self._highlight(new_idx)
        self._emit_changed()

    def _op_add_atom_free(self, cx: float, cy: float):
        rwmol = Chem.RWMol(self._mol)
        new_idx = rwmol.AddAtom(Chem.Atom(self._atom_type))
        AllChem.Compute2DCoords(rwmol)
        self._mol = rwmol
        self._tags = self._update_tags_after_edit()
        self._highlight(new_idx)
        self._emit_changed()

    def _op_add_bond(self, atom_a: int, atom_b: int):
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
        rwmol = Chem.RWMol(self._mol)
        bond = rwmol.GetBondWithIdx(bond_idx)
        rwmol.RemoveBond(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx())
        AllChem.Compute2DCoords(rwmol)
        self._mol = rwmol
        self._tags = self._update_tags_after_edit()
        self._selected_bond = None
        self._render()
        self._emit_changed()
        self.update()

    def _update_tags_after_edit(self):
        """编辑后调整 tag 索引（暂未实现，保持原样）。"""
        return self._tags

    def _emit_changed(self):
        self.smiles_changed.emit(self.get_esmiles())

    # ---- Layer 1 叠加层绘制 ----

    def _paint_overlay(self, painter: QPainter):
        """在 RDKit 骨架上叠加 E-SMILES 扩展标签."""
        if self._mol is None:
            return

        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. 收集每个原子上的所有 <a> 标签（按 index 分组）
        atom_tags: dict[int, list[ESmilesTag]] = {}
        for tag in self._tags:
            if tag.type == "a":
                atom_tags.setdefault(tag.index, []).append(tag)

        # 2. 绘制 <a> 标签气泡
        for atom_idx, tags in atom_tags.items():
            try:
                pt = self._drawer.GetDrawCoords(atom_idx)
            except Exception:
                continue
            wx, wy = self._canvas_to_widget(pt.x, pt.y)
            self._draw_tag_bubbles(painter, wx, wy, tags)

        # 3. 绘制 <dum> 虚拟原子（atomic_num == 0 的 * 原子）
        self._draw_dummy_atoms(painter)

    def _draw_tag_bubbles(self, painter: QPainter,
                           wx: float, wy: float,
                           tags: list[ESmilesTag]):
        """在原子旁边绘制一组标签气泡."""
        font = QFont("Arial", 8)
        painter.setFont(font)
        fm = painter.fontMetrics()

        for i, tag in enumerate(tags):
            text = tag.group
            tw = fm.horizontalAdvance(text)
            th = fm.height()
            # 气泡背景：文字四周各留 3px padding
            bw = tw + 6
            bh = th + 4
            # 多个标签垂直堆叠，向上偏移
            bx = wx + 6
            by = wy - 14 - i * (bh + 2)

            bg = _tag_bg_color(tag)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(int(bx), int(by), int(bw), int(bh), 3, 3)

            # 文字
            fg = QColor(255, 255, 255, 255) if bg.red() < 150 else QColor(30, 30, 30, 255)
            painter.setPen(fg)
            painter.drawText(int(bx + 3), int(by + bh - 4), text)

    def _draw_dummy_atoms(self, painter: QPainter):
        """在所有虚拟原子（atomic_num=0）位置绘制菱形标记."""
        if self._mol is None:
            return
        for atom_idx in range(self._mol.GetNumAtoms()):
            atom = self._mol.GetAtomWithIdx(atom_idx)
            if atom.GetAtomicNum() != 0:
                continue
            try:
                pt = self._drawer.GetDrawCoords(atom_idx)
            except Exception:
                continue
            wx, wy = self._canvas_to_widget(pt.x, pt.y)
            size = 5 * self._transform.scale  # 菱形半尺寸，随缩放变化

            # 菱形4个顶点（旋转45°）
            cx, cy = wx, wy
            diamond = [
                (cx, cy - size),    # 上
                (cx + size, cy),    # 右
                (cx, cy + size),    # 下
                (cx - size, cy),    # 左
            ]
            from PyQt6.QtGui import QPolygon
            poly = QPolygon([QPoint(int(x), int(y)) for x, y in diamond])

            painter.setPen(QPen(QColor(230, 120, 30), 1))
            painter.setBrush(QColor(255, 200, 80, 220))
            painter.drawPolygon(poly)

    # ---- Qt Events ----

    def paintEvent(self, event):
        if self._pixmap is None or self._pixmap.isNull():
            p = ThemeManager.instance().palette()
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor(p["bg_card"]))
            painter.end()
            return

        # 绘制骨架层
        painter = QPainter(self)
        scaled = self._pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)

        # 叠加层（Layer 1）
        self._paint_overlay(painter)
        painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_transform()
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._mol is None:
            return

        wx, wy = event.position().x(), event.position().y()
        cx, cy = self._widget_to_canvas(wx, wy)
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
