"""项目文件树."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from ..core.project import Project
from ..utils.constants import PROJECT_META_DIR, SUPPORTED_DOC_EXTS, SUPPORTED_MOL_EXTS
from .theme import ThemeManager


class FileTreeWidget(QTreeWidget):
    """文件树组件（支持增量更新与懒加载）."""

    file_selected = pyqtSignal(Path)
    file_opened = pyqtSignal(Path)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.project: Project | None = None
        self.setHeaderLabel("项目文件")
        self.setColumnCount(1)
        self.itemDoubleClicked.connect(self._on_double_click)
        self.itemExpanded.connect(self._on_item_expanded)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def set_project(self, project: Project):
        """设置项目并完全刷新树."""
        self.project = project
        self.refresh()

    def refresh(self):
        """完全重建文件树（适合初始加载或大幅变更）."""
        self.clear()
        if self.project is None:
            return

        root_item = QTreeWidgetItem(self)
        root_item.setText(0, self.project.name)
        root_item.setData(0, Qt.ItemDataRole.UserRole, self.project.root)
        # 根目录预加载第一层（展开显示）
        self._populate_tree(self.project.root, root_item, depth=0)
        root_item.setExpanded(True)
        self.addTopLevelItem(root_item)

    def _populate_tree(
        self, dir_path: Path, parent_item: QTreeWidgetItem, depth: int = 0, max_depth: int = 1
    ):
        """递归填充目录树.

        Args:
            dir_path: 当前目录路径
            parent_item: 父树节点
            depth: 当前深度
            max_depth: 最大预加载深度（超出则标记为懒加载）
        """
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
                elif entry.is_file() and entry.suffix.lower() in (
                    SUPPORTED_DOC_EXTS | SUPPORTED_MOL_EXTS
                ):
                    files.append(entry)

            for d in dirs:
                item = QTreeWidgetItem(parent_item)
                item.setText(0, d.name + "/")
                item.setData(0, Qt.ItemDataRole.UserRole, d)
                if depth < max_depth:
                    self._populate_tree(d, item, depth=depth + 1, max_depth=max_depth)
                else:
                    # 标记为未加载，展开时再填充
                    item.setData(0, Qt.ItemDataRole.UserRole + 1, False)
                    # 添加占位子项以显示展开箭头
                    placeholder = QTreeWidgetItem(item)
                    placeholder.setText(0, "加载中...")

            for f in files:
                item = QTreeWidgetItem(parent_item)
                item.setText(0, f.name)
                item.setData(0, Qt.ItemDataRole.UserRole, f)
        except PermissionError:
            pass

    def _on_item_expanded(self, item: QTreeWidgetItem):
        """展开节点时触发懒加载."""
        loaded = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if loaded is not False:
            return

        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path is None or not Path(path).is_dir():
            return

        # 移除占位子项
        while item.childCount() > 0:
            item.removeChild(item.child(0))

        # 加载实际内容
        self._populate_tree(Path(path), item, depth=999, max_depth=999)
        item.setData(0, Qt.ItemDataRole.UserRole + 1, True)

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

    def get_selected_path(self) -> Path | None:
        item = self.currentItem()
        if item:
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path:
                return Path(path)
        return None

    def _on_theme_changed(self, mode: str):
        self.refresh()
