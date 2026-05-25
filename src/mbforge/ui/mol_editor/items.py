"""分子编辑器 QGraphicsScene 渲染层 — AtomItem / BondItem / TagItem."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import QLineF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
)

from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem.Draw import rdMolDraw2D

from ...molecules.esmiles import ESmilesTag


# ---- Editor Tools ----

class EditorTool(Enum):
    SELECT = "select"
    ADD_ATOM = "add_atom"
    ADD_BOND = "add_bond"
    DELETE = "delete"

# ---- 全局缩放因子 ----
# RDKit 2D 坐标 ~1.5 Å/键长，SCALE 将其映射到像素，1 scene_unit = 1 pixel
SCALE = 50

_ELEMENT_COLORS = {
    "C": QColor(0, 0, 0),
    "N": QColor(50, 50, 200),
    "O": QColor(220, 50, 50),
    "S": QColor(200, 180, 50),
    "P": QColor(250, 130, 20),
    "F": QColor(130, 200, 50),
    "Cl": QColor(50, 200, 50),
    "Br": QColor(180, 80, 50),
    "I": QColor(140, 50, 180),
    "H": QColor(200, 200, 200),
}


# ---- 数据结构（适配层输出） ----

@dataclass
class AtomNode:
    """原子节点描述 — 从 RDKit Mol 提取的纯数据."""
    atom_idx: int
    element: str
    x: float
    y: float
    charge: int = 0
    is_dummy: bool = False


@dataclass
class BondEdge:
    """化学键描述 — 从 RDKit Mol 提取的纯数据."""
    bond_idx: int
    from_idx: int
    to_idx: int
    bond_type: float  # Chem.BondType as double
    is_in_ring: bool = False


@dataclass
class RingDesc:
    """环描述 — 从 RDKit RingInfo 提取."""
    ring_idx: int
    atom_indices: list[int]
    center_x: float = 0.0
    center_y: float = 0.0


# ---- MolGraphAdapter ----

class MolGraphAdapter:
    """从 RDKit Mol 提取轻量渲染描述 — 无 RDKit 引用泄漏到渲染层."""

    def __init__(self, mol: Chem.ROMol):
        self.mol = mol
        self.atoms: list[AtomNode] = []
        self.bonds: list[BondEdge] = []
        self.rings: list[RingDesc] = []
        self._extract()

    def _extract(self):
        mol = self.mol
        conf = mol.GetConformer()

        for atom in mol.GetAtoms():
            idx = atom.GetIdx()
            pos = conf.GetAtomPosition(idx)
            self.atoms.append(AtomNode(
                atom_idx=idx,
                element=atom.GetSymbol(),
                x=pos.x * SCALE,
                y=pos.y * SCALE,
                charge=atom.GetFormalCharge(),
                is_dummy=(atom.GetAtomicNum() == 0),
            ))

        for bond in mol.GetBonds():
            self.bonds.append(BondEdge(
                bond_idx=bond.GetIdx(),
                from_idx=bond.GetBeginAtomIdx(),
                to_idx=bond.GetEndAtomIdx(),
                bond_type=bond.GetBondTypeAsDouble(),
                is_in_ring=bond.IsInRing(),
            ))

        ring_info = mol.GetRingInfo()
        for ring_idx, atom_ring in enumerate(ring_info.AtomRings()):
            cx = cy = 0.0
            for a_idx in atom_ring:
                pos = conf.GetAtomPosition(a_idx)
                cx += pos.x
                cy += pos.y
            n = len(atom_ring)
            self.rings.append(RingDesc(
                ring_idx=ring_idx,
                atom_indices=list(atom_ring),
                center_x=cx / n * SCALE,
                center_y=cy / n * SCALE,
            ))

    def atom_by_idx(self, idx: int) -> AtomNode | None:
        for a in self.atoms:
            if a.atom_idx == idx:
                return a
        return None


# ---- QGraphicsItem 实现 ----

class AtomItem(QGraphicsObject):
    """原子节点 Item — 圆形元素色，拖拽移动，端点自动跟随."""

    clicked = pyqtSignal(int)  # atom_idx
    moved = pyqtSignal(int, float, float)  # atom_idx, x, y

    RADIUS = 12.0  # scene units — fitInView 后约 30-40px 直径，确保可点击和显示符号

    def __init__(self, atom: AtomNode, parent=None):
        super().__init__(parent)
        self.atom_idx = atom.atom_idx
        self.element = atom.element
        self.is_dummy = atom.is_dummy
        self._selected = False
        self._highlight_color: QColor | None = None
        self._bond_items: set = set()  # 关联的 BondItem

        self.setPos(atom.x, atom.y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

    def add_bond(self, bond_item):
        self._bond_items.add(bond_item)

    def set_selected(self, selected: bool):
        self._selected = selected
        self.update()

    def set_highlight_color(self, color: QColor | None):
        self._highlight_color = color
        self.update()

    def boundingRect(self) -> QRectF:
        r = self.RADIUS * 2.5
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.RADIUS

        if self.is_dummy:
            s = r * 1.4
            path = QPainterPath()
            path.moveTo(0, -s)
            path.lineTo(s, 0)
            path.lineTo(0, s)
            path.lineTo(-s, 0)
            path.closeSubpath()
            painter.fillPath(path, QColor(255, 200, 80, 220))
            painter.setPen(QPen(QColor(230, 120, 30), 2.0))
            painter.drawPath(path)
            font = QFont()
            font.setPointSize(max(10, 1))
            painter.setFont(font)
            painter.setPen(QColor(60, 30, 0))
            painter.drawText(int(-r * 0.4), int(r * 0.3), "*")
            return

        color = _ELEMENT_COLORS.get(self.element, QColor(150, 150, 150))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QRectF(-r, -r, r * 2, r * 2))

        if self._selected:
            painter.setPen(QPen(QColor(255, 220, 50), 3.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(-r, -r, r * 2, r * 2))
        elif self._highlight_color:
            painter.setPen(QPen(self._highlight_color, 3.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(-r, -r, r * 2, r * 2))

        font = QFont()
        font.setPointSize(max(10, 1))
        painter.setFont(font)
        text_color = QColor(255, 255, 255) if color.red() < 150 else QColor(20, 20, 20)
        painter.setPen(text_color)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(self.element)
        painter.drawText(int(-tw / 2), int(r * 0.35), self.element)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.atom_idx)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        scene_pos = self.scenePos()
        self.moved.emit(self.atom_idx, scene_pos.x(), scene_pos.y())

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for bond_item in self._bond_items:
                bond_item.update_geometry()
        return super().itemChange(change, value)


class BondItem(QGraphicsObject):
    """化学键 Item — 绑定到两个 AtomItem，几何端点自动跟随."""

    clicked = pyqtSignal(int)  # bond_idx

    def __init__(self, bond: BondEdge, atom_a: AtomItem, atom_b: AtomItem, parent=None):
        super().__init__(parent)
        self.bond_idx = bond.bond_idx
        self.from_idx = bond.from_idx
        self.to_idx = bond.to_idx
        self.bond_type = bond.bond_type
        self._atom_a = atom_a
        self._atom_b = atom_b
        self._selected = False
        self._pending = False

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        atom_a.add_bond(self)
        atom_b.add_bond(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.bond_idx)
        super().mousePressEvent(event)

    def update_geometry(self):
        self.prepareGeometryChange()
        self.update()

    def set_selected(self, selected: bool):
        self._selected = selected
        self.update()

    def set_pending(self, pending: bool):
        self._pending = pending
        self.update()

    def boundingRect(self) -> QRectF:
        ax = self._atom_a.scenePos().x()
        ay = self._atom_a.scenePos().y()
        bx = self._atom_b.scenePos().x()
        by = self._atom_b.scenePos().y()
        pad = 3.0
        return QRectF(
            min(ax, bx) - pad, min(ay, by) - pad,
            abs(bx - ax) + pad * 2, abs(by - ay) + pad * 2
        )

    def paint(self, painter: QPainter, option, widget=None):
        ax = float(self._atom_a.scenePos().x())
        ay = float(self._atom_a.scenePos().y())
        bx = float(self._atom_b.scenePos().x())
        by = float(self._atom_b.scenePos().y())

        # 键端点取原子边缘（AtomItem.RADIUS），不取圆心
        r = AtomItem.RADIUS
        dx = bx - ax
        dy = by - ay
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 0.001:
            return
        ux = dx / dist
        uy = dy / dist
        # 从 atom A 边缘到 atom B 边缘
        x1 = ax + ux * r
        y1 = ay + uy * r
        x2 = bx - ux * r
        y2 = by - uy * r

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._selected:
            pen = QPen(QColor(100, 140, 220, 220), 2.0)
        elif self._pending:
            pen = QPen(QColor(100, 180, 100, 220), 2.0)
        else:
            pen = QPen(Qt.GlobalColor.black, 1.5)

        bond_type = self.bond_type

        if abs(bond_type - 1.0) < 0.01:
            painter.setPen(pen)
            painter.drawLine(QLineF(x1, y1, x2, y2))
        elif abs(bond_type - 2.0) < 0.01:
            self._draw_multi(painter, x1, y1, x2, y2, 2, pen)
        elif abs(bond_type - 3.0) < 0.01:
            self._draw_multi(painter, x1, y1, x2, y2, 3, pen)
        elif abs(bond_type - 1.5) < 0.01:
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidthF(1.5)
            painter.setPen(pen)
            painter.drawLine(QLineF(x1, y1, x2, y2))
        else:
            painter.setPen(pen)
            painter.drawLine(QLineF(x1, y1, x2, y2))

    def _draw_multi(self, painter, ax, ay, bx, by, n, pen):
        dx = bx - ax
        dy = by - ay
        length = math.sqrt(dx * dx + dy * dy)
        if length < 0.001:
            return
        ux = -dy / length
        uy = dx / length
        offset = 2.5

        for i in range(n):
            off = (i - (n - 1) / 2) * offset
            px1 = ax + ux * off
            py1 = ay + uy * off
            px2 = bx + ux * off
            py2 = by + uy * off
            painter.setPen(pen)
            painter.drawLine(QLineF(px1, py1, px2, py2))


class TagGraphicsItem(QGraphicsObject):
    """E-SMILES <a> 标签气泡 — 挂载为 AtomItem 子项，自动跟随原子移动."""

    def __init__(self, tag: ESmilesTag, parent_atom: AtomItem, stack_offset: int = 0):
        super().__init__(parent_atom)  # 子项，坐标相对于父原子
        self.tag = tag
        self._stack_offset = stack_offset
        self._text = tag.group
        r = AtomItem.RADIUS
        self._ox = r * 0.3
        self._oy = -r * 1.3 - stack_offset * r * 0.7
        self._apply_color()
        self.setPos(self._ox, self._oy)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresParentOpacity)

    def _apply_color(self):
        color_map = {
            "R[1]": QColor(220, 50, 50),
            "R[2]": QColor(50, 100, 220),
            "R[3]": QColor(50, 180, 80),
            "R[4]": QColor(180, 80, 200),
            "R[5]": QColor(220, 140, 30),
        }
        self._bg = color_map.get(self.tag.group, QColor(240, 220, 80))
        self._fg = QColor(255, 255, 255) if self._bg.red() < 160 else QColor(30, 30, 30)

    def boundingRect(self) -> QRectF:
        r = AtomItem.RADIUS
        return QRectF(-2, -r * 0.6, r * 2.8, r * 1.0)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont()
        font.setPointSize(max(10, 1))
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = max(1, fm.horizontalAdvance(self._text))
        th = max(1, fm.height())
        pad = 4
        bw = tw + pad * 2
        bh = th + pad

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._bg)
        painter.drawRoundedRect(0, 0, int(bw), int(bh), 4, 4)
        painter.setPen(self._fg)
        painter.drawText(pad, int(bh - pad - 1), self._text)


class RingTagGraphicsItem(QGraphicsObject):
    """E-SMILES <r>（键中点）和 <c>（环中心）标签 — 独立绘制，不挂载到 AtomItem."""

    def __init__(self, tag: ESmilesTag, x: float, y: float):
        super().__init__()
        self.tag = tag
        self.setPos(x, y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresParentOpacity)

        color_map = {
            "R[1]": QColor(220, 50, 50),
            "R[2]": QColor(50, 100, 220),
            "R[3]": QColor(50, 180, 80),
            "R[4]": QColor(180, 80, 200),
            "R[5]": QColor(220, 140, 30),
        }
        self._color = color_map.get(tag.group, QColor(160, 100, 200))

    def boundingRect(self) -> QRectF:
        r = AtomItem.RADIUS * 1.5
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r, g, b = self._color.red(), self._color.green(), self._color.blue()
        size = AtomItem.RADIUS * 0.5

        if self.tag.type == "r":
            path = QPainterPath()
            path.moveTo(0, -size)
            path.lineTo(size, 0)
            path.lineTo(0, size)
            path.lineTo(-size, 0)
            path.closeSubpath()
            painter.fillPath(path, QColor(r, g, b, 200))
            painter.setPen(QPen(QColor(r, g, b), 2.0))
            painter.drawPath(path)
            font = QFont()
            font.setPointSize(max(9, 1))
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(int(-size * 1.5), int(size * 0.5), self.tag.group)
        else:
            radius = AtomItem.RADIUS * 0.8
            painter.setPen(QPen(QColor(180, 80, 200), 2.0))
            painter.setBrush(QColor(200, 120, 230, 120))
            painter.drawEllipse(int(-radius), int(-radius), int(radius * 2), int(radius * 2))
            font = QFont()
            font.setPointSize(max(9, 1))
            painter.setFont(font)
            painter.setPen(QColor(60, 30, 80))
            painter.drawText(int(-radius * 1.2), int(radius * 0.4), self.tag.group)


class BackgroundItem(QGraphicsPixmapItem):
    """复杂分子的 RDKit 渲染底图 — 作为背景层（zValue = -1）。"""

    def __init__(self, mol: Chem.ROMol, width: int = 500, height: int = 500):
        super().__init__()
        drawer = rdMolDraw2D.MolDraw2DCairo(width, height)
        drawer.drawOptions().addAtomIndices = False
        drawer.drawOptions().addBondIndices = False
        rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
        drawer.FinishDrawing()
        img_bytes = drawer.GetDrawingText()
        pixmap = QPixmap.fromImage(QImage.fromData(img_bytes))
        self.setPixmap(pixmap)
        self.setZValue(-1)


# ---- MolEditorScene ----

class MolEditorScene(QGraphicsView):
    """分子编辑器 QGraphicsScene + View — Scene 坐标系 = RDKit 2D 坐标（1:1 映射）."""

    #: E-SMILES 变化时发出
    smiles_changed = pyqtSignal(str)
    #: 原子被点击（参数: atom_idx）
    atom_clicked = pyqtSignal(int)
    #: 键被点击（参数: bond_idx）
    bond_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mol: Chem.ROMol | None = None
        self._tags: list[ESmilesTag] = []
        self._adapter: MolGraphAdapter | None = None
        self._atom_items: dict[int, AtomItem] = {}
        self._bond_items: dict[int, BondItem] = {}
        self._tag_items: list[QGraphicsItem] = []
        self._bg_item: BackgroundItem | None = None

        self._scene = QGraphicsScene(self)
        self._scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor(248, 248, 248))
        self.setFrameShape(QFrame.Shape.NoFrame)

    def set_esmiles(self, esmiles: str, fit_view: bool = True):
        """加载 E-SMILES，重建 Scene."""
        from ...molecules.esmiles import esmiles_to_mol
        try:
            self._mol, self._tags = esmiles_to_mol(esmiles)
        except ValueError:
            self._mol = None
            self._tags = []
            self._clear_scene()
            return

        self._clear_scene()
        self._build_scene()
        if fit_view:
            self._fit_to_view()
        self.update()

    def get_esmiles(self) -> str:
        """获取当前 E-SMILES。"""
        if self._mol is None:
            return ""
        from ...molecules.esmiles import mol_to_esmiles
        return mol_to_esmiles(self._mol, self._tags)

    def _clear_scene(self):
        self._atom_items.clear()
        self._bond_items.clear()
        for item in self._tag_items:
            self._scene.removeItem(item)
        self._tag_items.clear()
        if self._bg_item:
            self._scene.removeItem(self._bg_item)
            self._bg_item = None
        self._scene.clear()

    def _build_scene(self):
        if self._mol is None:
            return

        AllChem.Compute2DCoords(self._mol)
        self._adapter = MolGraphAdapter(self._mol)

        # 复杂分子启用 RDKit 底图（暂时禁用以避免坐标对齐问题）
        # if self._mol.GetNumAtoms() > 30 or len(self._adapter.rings) > 3:
        #     self._bg_item = BackgroundItem(self._mol)
        #     self._scene.addItem(self._bg_item)
        self._bg_item = None

        # 创建 AtomItem
        for atom in self._adapter.atoms:
            item = AtomItem(atom)
            item.clicked.connect(self._on_atom_clicked)
            item.moved.connect(self._on_atom_moved)
            self._scene.addItem(item)
            self._atom_items[atom.atom_idx] = item

        # 创建 BondItem
        for bond in self._adapter.bonds:
            a_item = self._atom_items.get(bond.from_idx)
            b_item = self._atom_items.get(bond.to_idx)
            if a_item is None or b_item is None:
                continue
            bond_item = BondItem(bond, a_item, b_item)
            bond_item.clicked.connect(self._on_bond_clicked)
            self._scene.addItem(bond_item)
            self._bond_items[bond.bond_idx] = bond_item

        # 创建 TagItem
        # 先按 atom_idx 分组，用于计算堆叠偏移
        atom_tag_counts: dict[int, int] = {}
        for tag in self._tags:
            if tag.type == "a" and tag.index in self._atom_items:
                atom_tag_counts[tag.index] = atom_tag_counts.get(tag.index, 0)

        atom_tag_stack: dict[int, int] = {}
        for tag in self._tags:
            if tag.type == "a" and tag.index in self._atom_items:
                parent = self._atom_items[tag.index]
                offset = atom_tag_stack.get(tag.index, 0)
                atom_tag_stack[tag.index] = offset + 1
                tag_item = TagGraphicsItem(tag, parent, stack_offset=offset)
                # TagGraphicsItem 子项随 parent AtomItem 自动加入 scene，无需 addItem
                self._tag_items.append(tag_item)
            elif tag.type == "r" and tag.index < len(self._adapter.bonds):
                bond = self._adapter.bonds[tag.index]
                ax = self._atom_items[bond.from_idx]
                bx = self._atom_items[bond.to_idx]
                cx = (ax.scenePos().x() + bx.scenePos().x()) / 2
                cy = (ax.scenePos().y() + bx.scenePos().y()) / 2
                tag_item = RingTagGraphicsItem(tag, cx, cy)
                self._scene.addItem(tag_item)
                self._tag_items.append(tag_item)
            elif tag.type == "c":
                ring = None
                for r in self._adapter.rings:
                    if r.ring_idx == tag.index:
                        ring = r
                        break
                if ring:
                    tag_item = RingTagGraphicsItem(tag, ring.center_x, ring.center_y)
                    self._scene.addItem(tag_item)
                    self._tag_items.append(tag_item)

    def _fit_to_view(self):
        if not self._scene.items():
            return
        rect = self._scene.itemsBoundingRect()
        if rect.isEmpty():
            return
        rect.adjust(-3, -3, 3, 3)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.centerOn(rect.center())

    def _on_atom_clicked(self, atom_idx: int):
        self.atom_clicked.emit(atom_idx)

    def _on_bond_clicked(self, bond_idx: int):
        self.bond_clicked.emit(bond_idx)

    def _on_atom_moved(self, atom_idx: int, x: float, y: float):
        if self._mol is None:
            return
        try:
            conf = self._mol.GetConformer()
            conf.SetAtomPosition(atom_idx, x, y)
        except Exception:
            pass

    def set_tool(self, tool: EditorTool):
        """切换工具模式（由外部调用）。"""
        self._current_tool = tool

    def set_atom_type(self, atom: str):
        self._atom_type = atom

    def set_bond_order(self, order: Chem.BondType):
        self._bond_order = order

    # ---- Viewport interaction: wheel zoom, right-drag pan ----

    def wheelEvent(self, event):
        """鼠标滚轮缩放。"""
        factor = 1.15
        if event.angleDelta().y() < 0:
            factor = 1.0 / factor
        self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._pan_last_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.RightButton and hasattr(self, '_pan_last_pos'):
            dx = self._pan_last_pos.x() - event.pos().x()
            dy = self._pan_last_pos.y() - event.pos().y()
            self._pan_last_pos = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + dx)
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + dy)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.unsetCursor()
            if hasattr(self, '_pan_last_pos'):
                del self._pan_last_pos
            return
        super().mouseReleaseEvent(event)
