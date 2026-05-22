"""分子数据面板."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHeaderView,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from ..core.mol_database import MoleculeDatabase, MoleculeRecord
from .dialogs import MoleculeInfoDialog
from .theme import create_table


class MoleculePanel(QWidget):
    """分子列表面板."""

    molecule_selected = pyqtSignal(MoleculeRecord)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.mol_db: Optional[MoleculeDatabase] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = create_table(["SMILES", "名称", "活性", "类型", "来源"], parent=self)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.table)

    def set_database(self, mol_db: MoleculeDatabase):
        self.mol_db = mol_db
        self.refresh()

    def refresh(self):
        self.table.setRowCount(0)
        if self.mol_db is None:
            return
        records = self.mol_db.list_all(limit=500)
        self.table.setRowCount(len(records))
        for i, rec in enumerate(records):
            from PyQt6.QtWidgets import QTableWidgetItem

            self.table.setItem(i, 0, QTableWidgetItem(rec.smiles))
            self.table.setItem(i, 1, QTableWidgetItem(rec.name))
            act_text = (
                f"{rec.activity} {rec.units}" if rec.activity is not None else "-"
            )
            self.table.setItem(i, 2, QTableWidgetItem(act_text))
            self.table.setItem(i, 3, QTableWidgetItem(rec.activity_type))
            self.table.setItem(
                i,
                4,
                QTableWidgetItem(
                    rec.source_doc[:20] + "..." if rec.source_doc else "-"
                ),
            )
            for col in range(5):
                item = self.table.item(i, col)
                if item:
                    item.setData(Qt.ItemDataRole.UserRole, rec)

    def _show_context_menu(self, position):
        item = self.table.itemAt(position)
        if item is None:
            return
        rec = item.data(Qt.ItemDataRole.UserRole)
        if rec is None:
            return

        menu = QMenu(self)
        view_action = menu.addAction("查看详情")
        export_action = menu.addAction("导出 SMILES")
        action = menu.exec(self.table.mapToGlobal(position))

        if action == view_action:
            dlg = MoleculeInfoDialog(rec, self)
            dlg.exec()
        elif action == export_action:
            from PyQt6.QtWidgets import QApplication

            QApplication.clipboard().setText(rec.smiles)
