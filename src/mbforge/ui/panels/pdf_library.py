"""文献库管理面板."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...core.project import Project
from ..components import EmptyStateWidget
from ..theme import ThemeManager, _p, SearchBox, create_button, create_label


class PDFLibraryPanel(QWidget):
    """文献库面板：展示项目中所有已索引的 PDF 文献."""

    pdf_opened = pyqtSignal(Path)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.project: Project | None = None
        self._pdfs: list = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # 标题栏
        header = QWidget()
        p = _p()
        header.setStyleSheet(f"border-bottom: 1px solid {p['border']};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 8)
        header_layout.setSpacing(8)

        title = create_label("文献库", level="header")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.refresh_btn = create_button("刷新", style="default")
        self.refresh_btn.clicked.connect(self.refresh)
        header_layout.addWidget(self.refresh_btn)
        layout.addWidget(header)

        # 搜索框
        self.search_box = SearchBox(placeholder="搜索文献标题...")
        self.search_box.returnPressed.connect(self._on_search)
        layout.addWidget(self.search_box)

        # 空状态 / 内容区堆叠
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # 空状态页
        self.empty_state = EmptyStateWidget(
            icon="📄",
            title="文献库为空",
            subtitle="请先索引项目文件",
        )
        self.stack.addWidget(self.empty_state)

        # 内容页：左右分栏
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        # 左侧：PDF 列表
        self.pdf_list = QListWidget()
        p = _p()
        self.pdf_list.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid {p['border']};
                border-radius: 10px;
                background: {p['bg_card']};
                outline: none;
            }}
            QListWidget::item {{
                padding: 10px 12px;
                border-bottom: 1px solid {p['border']};
            }}
            QListWidget::item:selected {{
                background: {p['brand_primary']}1a;
                color: {p['brand_primary']};
            }}
            QListWidget::item:hover {{
                background: {p['bg_hover']};
            }}
        """)
        self.pdf_list.itemDoubleClicked.connect(self._open_selected)
        splitter.addWidget(self.pdf_list)

        # 右侧：PDF 详情
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setSpacing(8)

        self.detail_header = create_label("双击打开文献", level="header")
        detail_layout.addWidget(self.detail_header)

        self.detail_meta = create_label("", level="caption")
        detail_layout.addWidget(self.detail_meta)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        p = _p()
        self.preview_text.setStyleSheet(f"""
            QTextEdit {{
                background: {p['bg_hover']};
                border: 1px solid {p['border']};
                border-radius: 10px;
                padding: 12px;
                font-size: 13px;
            }}
        """)
        detail_layout.addWidget(self.preview_text, 1)

        btn_layout = QHBoxLayout()
        self.open_btn = create_button("打开", style="primary")
        self.open_btn.clicked.connect(self._open_selected)
        btn_layout.addWidget(self.open_btn)

        self.index_btn = create_button("重新索引", style="secondary")
        self.index_btn.clicked.connect(self._reindex_selected)
        btn_layout.addWidget(self.index_btn)
        btn_layout.addStretch()
        detail_layout.addLayout(btn_layout)

        splitter.addWidget(detail_widget)
        splitter.setSizes([360, 540])
        content_layout.addWidget(splitter)
        self.stack.addWidget(content)

        self.stack.setCurrentIndex(1)  # 默认显示内容页（空时会切到空状态）

        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, mode: str):
        self.refresh()

    def set_project(self, project: Project):
        """设置项目实例."""
        self.project = project
        self.refresh()

    def refresh(self):
        """刷新文献列表."""
        self.pdf_list.clear()
        self._pdfs = []
        self.preview_text.clear()
        self.detail_meta.setText("")
        self.detail_header.setText("双击打开文献")

        if self.project is None:
            self.stack.setCurrentWidget(self.empty_state)
            return

        entries = self.project.list_documents()
        pdf_entries = [e for e in entries if e.doc_type == "pdf"]
        if not pdf_entries:
            self.stack.setCurrentWidget(self.empty_state)
            return

        self.stack.setCurrentWidget(self.stack.widget(1))  # 内容页
        for entry in pdf_entries:
            self._pdfs.append(entry)
            title = entry.path.name
            status = "已索引" if entry.indexed else "未索引"
            item = QListWidgetItem(f"{title}\n{status}")
            item.setData(Qt.ItemDataRole.UserRole, len(self._pdfs) - 1)
            self.pdf_list.addItem(item)

    def _on_search(self):
        """按标题搜索过滤."""
        query = self.search_box.text().strip().lower()
        self.pdf_list.clear()
        if not query:
            self.refresh()
            return
        for i, entry in enumerate(self._pdfs):
            if query in entry.path.name.lower():
                title = entry.path.name
                status = "已索引" if entry.indexed else "未索引"
                item = QListWidgetItem(f"{title}\n{status}")
                item.setData(Qt.ItemDataRole.UserRole, i)
                self.pdf_list.addItem(item)

    def _open_selected(self):
        """打开选中的 PDF."""
        current = self.pdf_list.currentItem()
        if current is None:
            return
        idx = current.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx < 0 or idx >= len(self._pdfs):
            return
        entry = self._pdfs[idx]
        self.pdf_opened.emit(entry.path)

    def _reindex_selected(self):
        """重新索引选中的 PDF（TODO）."""
        pass
