"""欢迎首页组件."""

from __future__ import annotations

import platform
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from ...utils.config import load_global_config
from ..components import EmptyStateWidget, InfoRow
from ..theme import CardWidget, ThemeManager, create_button, create_label


class WelcomeWidget(QWidget):
    """欢迎首页：展示最近项目、快捷操作和统计信息."""

    open_project_requested = pyqtSignal(Path)
    new_project_requested = pyqtSignal()
    open_settings_requested = pyqtSignal()
    start_services_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        # 主题切换时可能重复调用：先清理旧布局
        if self.layout() is not None:
            old = self.layout()
            while old.count():
                item = old.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            # 将旧布局转移到临时 widget，从而释放本 widget
            QWidget().setLayout(old)

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ==================== 左侧边栏：最近项目 ====================
        sidebar = QWidget()
        sidebar.setFixedWidth(300)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(20, 24, 20, 24)
        sidebar_layout.setSpacing(16)

        sidebar_title = create_label("最近项目", level="header")
        sidebar_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        sidebar_layout.addWidget(sidebar_title)

        self.recent_layout = QVBoxLayout()
        self.recent_layout.setSpacing(8)
        self.recent_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        sidebar_layout.addLayout(self.recent_layout)

        sidebar_layout.addStretch()
        root_layout.addWidget(sidebar)

        # 分隔线
        divider = QWidget()
        divider.setFixedWidth(1)
        p = ThemeManager.instance().palette()
        divider.setStyleSheet(f"background: {p['border']};")
        root_layout.addWidget(divider)

        # ==================== 右侧主区域 ====================
        main_area = QWidget()
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(24)

        # 标题区
        title = create_label("欢迎来到 MBForge", level="header")
        title.setStyleSheet("font-size: 28px; font-weight: 700;")
        main_layout.addWidget(title)

        subtitle = create_label(
            "分子科学知识库与 AI 工作台 — 像 Obsidian 一样管理，像 Zotero 一样引用",
            level="caption",
        )
        subtitle.setStyleSheet("font-size: 15px;")
        main_layout.addWidget(subtitle)

        main_layout.addSpacing(20)

        # 快捷操作卡片
        actions_card = CardWidget("快捷操作")
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(12)

        btn_new = create_button("新建项目", style="primary")
        btn_new.clicked.connect(lambda: self.new_project_requested.emit())
        actions_layout.addWidget(btn_new)

        btn_open = create_button("打开项目")
        btn_open.clicked.connect(self._open_project)
        actions_layout.addWidget(btn_open)

        btn_settings = create_button("设置")
        btn_settings.clicked.connect(lambda: self.open_settings_requested.emit())
        actions_layout.addWidget(btn_settings)

        btn_start_ai = create_button("启动 AI 服务")
        btn_start_ai.clicked.connect(lambda: self.start_services_requested.emit())
        actions_layout.addWidget(btn_start_ai)

        actions_layout.addStretch()
        actions_card.add_layout(actions_layout)
        main_layout.addWidget(actions_card)

        # 统计信息
        stats_card = CardWidget("系统状态")
        self.stats_layout = QHBoxLayout()
        self.stats_layout.setSpacing(20)
        stats_card.add_layout(self.stats_layout)
        main_layout.addWidget(stats_card)

        main_layout.addStretch()
        root_layout.addWidget(main_area, 1)

        self._refresh_recent_projects()
        self._refresh_stats()

        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, mode: str):
        """Refresh UI when theme changes."""
        self._setup_ui()
        self._refresh_recent_projects()
        self._refresh_stats()

    def _refresh_recent_projects(self):
        """刷新最近项目列表."""
        # 清空旧内容
        while self.recent_layout.count():
            item = self.recent_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        config = load_global_config()
        valid_projects = []
        for path_str in config.recent_projects[:5]:
            path = Path(path_str)
            if path.exists():
                valid_projects.append(path)

        if not valid_projects:
            empty = EmptyStateWidget(
                icon="",
                title="暂无最近项目",
                subtitle="点击上方「新建项目」或「打开项目」开始",
            )
            self.recent_layout.addWidget(empty)
            return

        for path in valid_projects:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 8, 8, 8)
            row_layout.setSpacing(12)
            p = ThemeManager.instance().palette()
            row.setStyleSheet(f"""
                QWidget {{
                    background: {p['bg_card']};
                    border: 1px solid {p['border']};
                    border-radius: 8px;
                }}
                QWidget:hover {{
                    background: {p['bg_hover']};
                }}
            """)

            name_label = create_label(path.name, level="header")
            row_layout.addWidget(name_label)

            path_label = create_label(str(path), level="caption")
            row_layout.addWidget(path_label, 1)

            open_btn = create_button("打开", style="primary")
            open_btn.clicked.connect(lambda checked, p=path: self.open_project_requested.emit(p))
            row_layout.addWidget(open_btn)

            self.recent_layout.addWidget(row)

    def _refresh_stats(self):
        """刷新系统状态统计."""
        while self.stats_layout.count():
            item = self.stats_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        stats = [
            ("文档", "0"),
            ("分子", "0"),
            ("索引片段", "0"),
        ]
        for label, value in stats:
            stat_widget = QWidget()
            stat_layout = QVBoxLayout(stat_widget)
            stat_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stat_layout.setSpacing(4)

            val_label = create_label(value, level="header")
            val_label.setStyleSheet("font-size: 20px; font-weight: 700;")
            stat_layout.addWidget(val_label, alignment=Qt.AlignmentFlag.AlignCenter)

            name_label = create_label(label, level="caption")
            stat_layout.addWidget(name_label, alignment=Qt.AlignmentFlag.AlignCenter)

            self.stats_layout.addWidget(stat_widget)

        # 系统信息
        sys_widget = QWidget()
        sys_layout = QVBoxLayout(sys_widget)
        sys_layout.setContentsMargins(8, 4, 8, 4)
        sys_layout.setSpacing(4)
        sys_layout.addWidget(InfoRow("平台", f"{platform.system()} {platform.release()}"))
        sys_layout.addWidget(InfoRow("Python", platform.python_version()))
        self.stats_layout.addWidget(sys_widget)

    def _open_project(self):
        from PyQt6.QtWidgets import QFileDialog

        path = QFileDialog.getExistingDirectory(self, "打开项目文件夹")
        if path:
            self.open_project_requested.emit(Path(path))

    def refresh(self):
        """外部调用刷新数据."""
        self._refresh_recent_projects()
        self._refresh_stats()
