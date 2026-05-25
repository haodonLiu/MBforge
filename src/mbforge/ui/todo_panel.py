"""TODO 队列管理面板."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ..core.todo_manager import TodoManager
from .components import EmptyStateWidget, SectionHeader
from .theme import CardWidget, ThemeManager, create_label


class TodoPanel(QWidget):
    """TODO 队列管理面板：展示待处理文件，支持进度可视化."""

    process_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.todo_manager: Optional[TodoManager] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # 头部
        header = SectionHeader(
            "TODO 队列",
            action_text="开始处理",
            action_callback=lambda: self.process_requested.emit(),
        )
        layout.addWidget(header)

        # 统计卡片
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)

        self.pending_card = CardWidget("待处理")
        self.pending_count = create_label("0", level="header")
        self.pending_count.setStyleSheet("font-size: 24px; font-weight: 700;")
        self.pending_card.add_widget(self.pending_count)
        stats_layout.addWidget(self.pending_card)

        self.processing_card = CardWidget("处理中")
        self.processing_count = create_label("0", level="header")
        self.processing_count.setStyleSheet("font-size: 24px; font-weight: 700;")
        self.processing_card.add_widget(self.processing_count)
        stats_layout.addWidget(self.processing_card)

        self.done_card = CardWidget("已完成")
        self.done_count = create_label("0", level="header")
        self.done_count.setStyleSheet("font-size: 24px; font-weight: 700;")
        self.done_card.add_widget(self.done_count)
        stats_layout.addWidget(self.done_card)

        layout.addLayout(stats_layout)

        # 总体进度
        p = ThemeManager.instance().palette()
        self.overall_progress = QProgressBar()
        self.overall_progress.setTextVisible(True)
        self.overall_progress.setStyleSheet(f"""
            QProgressBar {{
                background: {p['bg_base']};
                border: none;
                border-radius: 6px;
                text-align: center;
                font-size: 12px;
            }}
            QProgressBar::chunk {{
                background: {p['brand_primary']};
                border-radius: 6px;
            }}
        """)
        layout.addWidget(self.overall_progress)

        # 队列列表
        self.todo_list = QListWidget()
        self.todo_list.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid {p['border']};
                border-radius: 10px;
                background: {p['bg_card']};
                outline: none;
            }}
            QListWidget::item {{
                padding: 10px 12px;
                border-bottom: 1px solid {p['bg_base']};
            }}
            QListWidget::item:selected {{
                background: {p['brand_primary']}1a;
                color: {p['brand_primary']};
            }}
        """)
        layout.addWidget(self.todo_list)

        # 空状态
        self.empty_state = EmptyStateWidget(
            title="队列空空如也",
            subtitle="导入文件后将自动加入 TODO 队列",
        )
        self.empty_state.setVisible(False)
        layout.addWidget(self.empty_state)
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def set_todo_manager(self, todo_manager: TodoManager):
        """设置 TODO 管理器."""
        self.todo_manager = todo_manager
        self.refresh()

    def refresh(self):
        """刷新队列列表和统计."""
        self.todo_list.clear()

        if self.todo_manager is None:
            self._update_counts(0, 0, 0)
            self.empty_state.setVisible(True)
            return

        try:
            pending = self.todo_manager.get_pending()
            processing = self.todo_manager.get_processing()
            done = self.todo_manager.get_completed()

            self._update_counts(len(pending), len(processing), len(done))

            all_items = []
            for item in processing:
                all_items.append((item, "processing"))
            for item in pending:
                all_items.append((item, "pending"))
            for item in done[-50:]:  # 只显示最近 50 个完成的
                all_items.append((item, "done"))

            if not all_items:
                self.empty_state.setVisible(True)
                return
            else:
                self.empty_state.setVisible(False)

            for item, status in all_items:
                filename = getattr(item, "filename", str(item))
                list_item = QListWidgetItem(filename)
                list_item.setData(Qt.ItemDataRole.UserRole, (item, status))
                if status == "processing":
                    list_item.setBackground(Qt.GlobalColor.lightYellow)
                elif status == "done":
                    list_item.setForeground(Qt.GlobalColor.darkGray)
                self.todo_list.addItem(list_item)

            # 更新总进度
            total = len(pending) + len(processing) + len(done)
            if total > 0:
                self.overall_progress.setMaximum(total)
                self.overall_progress.setValue(len(done))
                self.overall_progress.setFormat(f"{len(done)}/{total}")
            else:
                self.overall_progress.setValue(0)
                self.overall_progress.setFormat("0/0")

        except Exception as e:
            self.todo_list.addItem(f"加载失败: {e}")

    def _update_counts(self, pending: int, processing: int, done: int):
        self.pending_count.setText(str(pending))
        self.processing_count.setText(str(processing))
        self.done_count.setText(str(done))

    def _on_theme_changed(self, mode: str):
        self.refresh()
