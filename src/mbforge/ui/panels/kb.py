"""知识库管理面板."""

from __future__ import annotations


from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...core.knowledge_base import KnowledgeBase
from ..components import EmptyStateWidget, SectionHeader
from ..theme import ThemeManager, _p, SearchBox, create_button, create_label


class KnowledgeBasePanel(QWidget):
    """知识库管理面板：展示索引片段，支持筛选和管理."""

    fragment_selected = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.kb: KnowledgeBase | None = None
        self._fragments: list[dict] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # 头部搜索
        header = SectionHeader("知识库", action_text="刷新", action_callback=self.refresh)
        layout.addWidget(header)

        self.search_box = SearchBox(placeholder="搜索知识库片段...")
        self.search_box.returnPressed.connect(self._on_search)
        layout.addWidget(self.search_box)

        # 主内容区分割
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：片段列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.fragment_list = QListWidget()
        p = _p()
        self.fragment_list.setStyleSheet(f"""
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
        self.fragment_list.currentItemChanged.connect(self._on_fragment_changed)
        left_layout.addWidget(self.fragment_list)
        splitter.addWidget(left_widget)

        # 右侧：片段详情
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.detail_header = create_label("选择片段查看详情", level="header")
        right_layout.addWidget(self.detail_header)

        self.detail_meta = create_label("", level="caption")
        right_layout.addWidget(self.detail_meta)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        p = _p()
        self.detail_text.setStyleSheet(f"""
            QTextEdit {{
                background: {p['bg_hover']};
                border: 1px solid {p['border']};
                border-radius: 10px;
                padding: 12px;
                font-size: 13px;
            }}
        """)
        right_layout.addWidget(self.detail_text)

        btn_layout = QHBoxLayout()
        self.reindex_btn = create_button("重新索引", style="primary")
        self.reindex_btn.setEnabled(False)
        self.reindex_btn.clicked.connect(self._reindex_current)
        btn_layout.addWidget(self.reindex_btn)

        self.delete_btn = create_button("删除", style="danger")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._delete_current)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addStretch()
        right_layout.addLayout(btn_layout)

        splitter.addWidget(right_widget)
        splitter.setSizes([360, 540])
        layout.addWidget(splitter)

        # 空状态
        self.empty_state = EmptyStateWidget(
            title="知识库为空",
            subtitle="请先索引项目文件",
        )
        self.empty_state.setVisible(False)
        layout.addWidget(self.empty_state)

        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, mode: str):
        self.refresh()

    def set_knowledge_base(self, kb: KnowledgeBase):
        """设置知识库实例."""
        self.kb = kb
        self.refresh()

    def refresh(self):
        """刷新片段列表."""
        self.fragment_list.clear()
        self._fragments = []
        self.detail_text.clear()
        self.reindex_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)

        if self.kb is None:
            self.empty_state.setVisible(True)
            return

        try:
            # 尝试从 ChromaDB 获取所有文档
            collection = self.kb.collection
            result = collection.get(include=["documents", "metadatas"])
            if result and result.get("ids"):
                ids = result["ids"]
                docs = result.get("documents") or []
                metas = result.get("metadatas") or []
                for i, doc_id in enumerate(ids):
                    doc = docs[i] if i < len(docs) else ""
                    meta = metas[i] if i < len(metas) else {}
                    self._fragments.append({
                        "id": doc_id,
                        "text": doc,
                        "metadata": meta,
                    })
                    title = meta.get("source", doc_id)[:40]
                    preview = doc[:80].replace("\n", " ") + "..."
                    item = QListWidgetItem(f"{title}\n{preview}")
                    item.setData(Qt.ItemDataRole.UserRole, i)
                    self.fragment_list.addItem(item)
            else:
                self.empty_state.setVisible(True)
        except Exception as e:
            self.detail_text.setPlainText(f"加载失败: {e}")

    def _on_search(self):
        """搜索过滤."""
        query = self.search_box.text().strip()
        if not query or self.kb is None:
            self.refresh()
            return
        try:
            results = self.kb.hybrid_search(query, top_k=20)
            self.fragment_list.clear()
            self._fragments = []
            for i, r in enumerate(results):
                self._fragments.append(r)
                preview = r.get("text", "")[:80].replace("\n", " ") + "..."
                item = QListWidgetItem(preview)
                item.setData(Qt.ItemDataRole.UserRole, i)
                self.fragment_list.addItem(item)
        except Exception as e:
            self.detail_text.setPlainText(f"搜索失败: {e}")

    def _on_fragment_changed(self, current: QListWidgetItem | None, previous):
        if current is None:
            return
        idx = current.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx < 0 or idx >= len(self._fragments):
            return

        frag = self._fragments[idx]
        text = frag.get("text", "")
        meta = frag.get("metadata", {})
        doc_id = frag.get("id", "")

        self.detail_header.setText(f"片段: {doc_id[:40]}...")
        meta_str = " | ".join(f"{k}: {v}" for k, v in meta.items())
        self.detail_meta.setText(meta_str[:200])
        self.detail_text.setPlainText(text)
        self.reindex_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        self.fragment_selected.emit(text)

    def _reindex_current(self):
        """重新索引当前片段（TODO：实现重索引逻辑）."""
        pass

    def _delete_current(self):
        """删除当前片段."""
        item = self.fragment_list.currentItem()
        if item is None:
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self._fragments):
            return
        frag = self._fragments[idx]
        doc_id = frag.get("id")
        if self.kb and doc_id:
            try:
                self.kb.collection.delete(ids=[doc_id])
                self.refresh()
            except Exception as e:
                self.detail_text.setPlainText(f"删除失败: {e}")
