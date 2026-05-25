"""分子数据面板."""

from __future__ import annotations

import csv
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.mol_database import MoleculeDatabase, MoleculeRecord
from ..utils.logger import get_logger
from .dialogs import MoleculeInfoDialog
from .mol_renderer import MoleculeImageWidget
from .theme import ThemeManager, _p, create_button, create_label, create_table

logger = get_logger(__name__)


class MoleculePanel(QWidget):
    """分子库管理面板.

    提供搜索过滤、表格展示、结构预览、导入导出、删除等功能。
    """

    molecule_selected = pyqtSignal(MoleculeRecord)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.mol_db: Optional[MoleculeDatabase] = None
        self._all_records: List[MoleculeRecord] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ---- 工具栏 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索名称 / SMILES / 来源...")
        self.search_input.returnPressed.connect(self.refresh)
        toolbar.addWidget(self.search_input, 3)

        self.act_min = QLineEdit()
        self.act_min.setPlaceholderText("活性 ≥")
        self.act_min.setMaximumWidth(80)
        self.act_min.returnPressed.connect(self.refresh)
        toolbar.addWidget(self.act_min, 1)

        self.act_max = QLineEdit()
        self.act_max.setPlaceholderText("活性 ≤")
        self.act_max.setMaximumWidth(80)
        self.act_max.returnPressed.connect(self.refresh)
        toolbar.addWidget(self.act_max, 1)

        self.refresh_btn = create_button("刷新")
        self.refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self.refresh_btn)

        self.import_btn = create_button("导入")
        self.import_btn.clicked.connect(self._import_csv)
        toolbar.addWidget(self.import_btn)

        self.export_btn = create_button("导出")
        self.export_btn.clicked.connect(self._export_csv)
        toolbar.addWidget(self.export_btn)

        layout.addLayout(toolbar)

        # ---- 统计信息 ----
        self.stats_label = create_label("未加载数据库", level="caption")
        p = _p()
        self.stats_label.setStyleSheet(f"padding: 4px 8px; color: {p['text_secondary']};")
        layout.addWidget(self.stats_label)

        # ---- 主体：表格 + 预览 ----
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 表格
        headers = ["SMILES", "名称", "活性", "类型", "MW", "LogP", "TPSA", "来源"]
        self.table = create_table(headers, parent=self)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 60)
        self.table.setColumnWidth(5, 60)
        self.table.setColumnWidth(6, 60)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.table)

        # 右侧预览
        preview = QWidget()
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        preview_layout.setSpacing(8)

        preview_header = create_label("结构预览", level="header")
        preview_layout.addWidget(preview_header)

        self.img_widget = MoleculeImageWidget(size=(320, 240))
        preview_layout.addWidget(self.img_widget)

        self.detail_label = create_label("选中分子查看详细信息", level="body")
        self.detail_label.setWordWrap(True)
        p = _p()
        self.detail_label.setStyleSheet(
            f"padding: 8px; background: {p['bg_hover']}; border-radius: 8px; border: 1px solid {p['border']};"
        )
        preview_layout.addWidget(self.detail_label)
        preview_layout.addStretch()

        splitter.addWidget(preview)
        splitter.setSizes([700, 340])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, mode: str):
        self.refresh()

    def set_database(self, mol_db: MoleculeDatabase):
        """绑定分子数据库并刷新显示."""
        self.mol_db = mol_db
        self.refresh()

    def refresh(self):
        """刷新表格数据，应用当前过滤条件."""
        self.table.setRowCount(0)
        if self.mol_db is None:
            self.stats_label.setText("未加载数据库")
            self.img_widget.clear()
            self.detail_label.setText("选中分子查看详细信息")
            return

        self._all_records = self.mol_db.list_all(limit=5000)
        filtered = self._filter_records(self._all_records)

        self.table.setRowCount(len(filtered))
        for i, rec in enumerate(filtered):
            props = rec.properties or {}
            self.table.setItem(i, 0, QTableWidgetItem(rec.smiles))
            self.table.setItem(i, 1, QTableWidgetItem(rec.name or "-"))
            act_text = (
                f"{rec.activity:.2f} {rec.units}"
                if rec.activity is not None
                else "-"
            )
            self.table.setItem(i, 2, QTableWidgetItem(act_text))
            self.table.setItem(i, 3, QTableWidgetItem(rec.activity_type or "-"))
            self.table.setItem(i, 4, QTableWidgetItem(str(props.get("MW", "-"))))
            self.table.setItem(i, 5, QTableWidgetItem(str(props.get("LogP", "-"))))
            self.table.setItem(i, 6, QTableWidgetItem(str(props.get("TPSA", "-"))))
            src = rec.source_doc[:20] + "..." if rec.source_doc else "-"
            self.table.setItem(i, 7, QTableWidgetItem(src))

            for col in range(self.table.columnCount()):
                item = self.table.item(i, col)
                if item:
                    item.setData(Qt.ItemDataRole.UserRole, rec)

        stats = self.mol_db.get_stats()
        self.stats_label.setText(
            f"共 {stats['total']} 个分子 | 有活性数据: {stats['with_activity']} 个"
            f" | 当前显示: {len(filtered)} 个"
        )

    def _filter_records(self, records: List[MoleculeRecord]) -> List[MoleculeRecord]:
        """根据搜索框和活性范围过滤记录."""
        query = self.search_input.text().strip().lower()
        min_act = self.act_min.text().strip()
        max_act = self.act_max.text().strip()

        result = records
        if query:
            result = [
                r
                for r in result
                if query in r.name.lower()
                or query in r.smiles.lower()
                or (r.source_doc and query in r.source_doc.lower())
                or any(query in t.lower() for t in r.tags)
            ]

        if min_act:
            try:
                min_v = float(min_act)
                result = [
                    r
                    for r in result
                    if r.activity is not None and r.activity >= min_v
                ]
            except ValueError:
                pass

        if max_act:
            try:
                max_v = float(max_act)
                result = [
                    r
                    for r in result
                    if r.activity is not None and r.activity <= max_v
                ]
            except ValueError:
                pass

        return result

    def _on_selection_changed(self):
        """表格选中行变化时更新右侧预览."""
        items = self.table.selectedItems()
        if not items:
            return
        rec = items[0].data(Qt.ItemDataRole.UserRole)
        if not isinstance(rec, MoleculeRecord):
            return

        self.molecule_selected.emit(rec)

        # 渲染结构
        self.img_widget.set_smiles(rec.smiles, legend=rec.name or "")

        # 更新详情
        props = rec.properties or {}
        lines = [
            f"<b>名称:</b> {rec.name or '-'}",
            f"<b>SMILES:</b> {rec.smiles}",
            (
                f"<b>活性:</b> {rec.activity} {rec.units}"
                if rec.activity is not None
                else "<b>活性:</b> -"
            ),
            f"<b>类型:</b> {rec.activity_type or '-'}",
            (
                f"<b>MW:</b> {props.get('MW', '-')} | "
                f"<b>LogP:</b> {props.get('LogP', '-')} | "
                f"<b>TPSA:</b> {props.get('TPSA', '-')}"
            ),
            (
                f"<b>HBD:</b> {props.get('HBD', '-')} | "
                f"<b>HBA:</b> {props.get('HBA', '-')}"
            ),
            f"<b>来源:</b> {rec.source_doc or '-'}",
            f"<b>标签:</b> {', '.join(rec.tags) or '-'}",
        ]
        self.detail_label.setText("<br>".join(lines))

    def _show_context_menu(self, position):
        """显示右键上下文菜单."""
        item = self.table.itemAt(position)
        if item is None:
            return
        rec = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(rec, MoleculeRecord):
            return

        menu = QMenu(self)
        view_action = menu.addAction("查看详情")
        export_action = menu.addAction("复制 SMILES")
        delete_action = menu.addAction("删除")
        action = menu.exec(self.table.mapToGlobal(position))

        if action == view_action:
            dlg = MoleculeInfoDialog(rec, self)
            dlg.exec()
        elif action == export_action:
            from PyQt6.QtWidgets import QApplication

            QApplication.clipboard().setText(rec.smiles)
            self.stats_label.setText(f"已复制 SMILES: {rec.smiles[:40]}...")
        elif action == delete_action:
            reply = QMessageBox.question(
                self,
                "确认删除",
                f"确定删除分子 {rec.name or rec.smiles[:30]}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes and self.mol_db:
                self.mol_db.delete_molecule(rec.mol_id)
                self.refresh()

    def _import_csv(self):
        """从 CSV 导入分子."""
        path, _ = QFileDialog.getOpenFileName(
            self, "导入分子 CSV", "", "CSV 文件 (*.csv);;所有文件 (*)"
        )
        if not path:
            return
        try:
            imported = 0
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    smiles = row.get("SMILES", "").strip()
                    if not smiles:
                        continue
                    rec = MoleculeRecord(
                        mol_id=row.get("id", smiles),
                        smiles=smiles,
                        name=row.get("name", ""),
                        activity=(
                            float(row["activity"]) if row.get("activity") else None
                        ),
                        activity_type=row.get("activity_type", ""),
                        units=row.get("units", "nM"),
                    )
                    if self.mol_db:
                        self.mol_db.add_molecule(rec)
                        imported += 1
            self.refresh()
            QMessageBox.information(self, "导入完成", f"成功导入 {imported} 个分子")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))
            logger.exception("导入分子 CSV 失败")

    def _export_csv(self):
        """导出分子到 CSV."""
        if self.mol_db is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出分子 CSV", "", "CSV 文件 (*.csv)"
        )
        if not path:
            return
        try:
            records = self.mol_db.list_all(limit=10000)
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "id",
                        "SMILES",
                        "name",
                        "activity",
                        "activity_type",
                        "units",
                        "MW",
                        "LogP",
                        "TPSA",
                        "source",
                    ]
                )
                for rec in records:
                    props = rec.properties or {}
                    writer.writerow(
                        [
                            rec.mol_id,
                            rec.smiles,
                            rec.name or "",
                            rec.activity,
                            rec.activity_type or "",
                            rec.units or "nM",
                            props.get("MW", ""),
                            props.get("LogP", ""),
                            props.get("TPSA", ""),
                            rec.source_doc or "",
                        ]
                    )
            QMessageBox.information(
                self, "导出完成", f"已导出 {len(records)} 个分子到 {path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
            logger.exception("导出分子 CSV 失败")
