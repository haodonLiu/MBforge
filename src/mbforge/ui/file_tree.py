"""项目文件树."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from ..core.project import Project
from ..utils.constants import PROJECT_META_DIR, SUPPORTED_DOC_EXTS, SUPPORTED_MOL_EXTS


class FileTreeWidget(QTreeWidget):
    """文件树组件."""

    file_selected = pyqtSignal(Path)
    file_opened = pyqtSignal(Path)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project: Optional[Project] = None
        self.setHeaderLabel("项目文件")
        self.setColumnCount(1)
        self.itemDoubleClicked.connect(self._on_double_click)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setStyleSheet("""
            QTreeWidget {
                border: none;
                background: #1e1e1e;
                color: #d4d4d4;
            }
            QTreeWidget::item:selected {
                background: #094771;
            }
            QTreeWidget::item:hover {
                background: #2a2d2e;
            }
        """)

    def set_project(self, project: Project):
        self.project = project
        self.refresh()

    def refresh(self):
        self.clear()
        if self.project is None:
            return

        root_item = QTreeWidgetItem(self)
        root_item.setText(0, self.project.name)
        root_item.setData(0, Qt.ItemDataRole.UserRole, self.project.root)
        self._populate_tree(self.project.root, root_item)
        root_item.setExpanded(True)
        self.addTopLevelItem(root_item)

    def _populate_tree(self, dir_path: Path, parent_item: QTreeWidgetItem):
        """递归填充目录树."""
        try:
            dirs = []
            files = []
            for entry in sorted(dir_path.iterdir(), key=lambda x: x.name.lower()):
                if entry.name.startswith("."):
                    continue
                if entry.name == PROJECT_META_DIR:
                    continue
                if entry.is_dir():
                    dirs.append(entry)
                elif entry.is_file() and entry.suffix.lower() in (SUPPORTED_DOC_EXTS | SUPPORTED_MOL_EXTS):
                    files.append(entry)

            for d in dirs:
                item = QTreeWidgetItem(parent_item)
                item.setText(0, d.name + "/")
                item.setData(0, Qt.ItemDataRole.UserRole, d)
                self._populate_tree(d, item)

            for f in files:
                item = QTreeWidgetItem(parent_item)
                item.setText(0, f.name)
                item.setData(0, Qt.ItemDataRole.UserRole, f)
        except PermissionError:
            pass

    def _on_double_click(self, item: QTreeWidgetItem, column: int):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and Path(path).is_file():
            self.file_opened.emit(Path(path))

    def _show_context_menu(self, position):
        item = self.itemAt(position)
        if item is None:
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path is None:
            return

        menu = QMenu(self)
        open_action = menu.addAction("打开")
        refresh_action = menu.addAction("刷新")
        menu.addSeparator()
        index_action = menu.addAction("索引到知识库")

        action = menu.exec(self.mapToGlobal(position))
        if action == open_action and Path(path).is_file():
            self.file_opened.emit(Path(path))
        elif action == refresh_action:
            self.refresh()
        elif action == index_action:
            self.file_selected.emit(Path(path))

    def get_selected_path(self) -> Optional[Path]:
        item = self.currentItem()
        if item:
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path:
                return Path(path)
        return None
