"""工作流中心面板."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from .components import EmptyStateWidget, SectionHeader, StatusBadge
from .theme import CardWidget, create_button, create_label


class WorkflowCard(CardWidget):
    """单个工作流模块卡片."""

    def __init__(
        self,
        icon: str,
        name: str,
        description: str,
        status: str = "offline",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(title=name, parent=parent)
        self._status = status

        # 图标 + 描述
        desc_layout = QHBoxLayout()
        icon_label = create_label(icon, level="header")
        icon_label.setStyleSheet("font-size: 32px;")
        desc_layout.addWidget(icon_label)

        info_layout = QVBoxLayout()
        desc_label = create_label(description, level="body")
        desc_label.setWordWrap(True)
        info_layout.addWidget(desc_label)

        self.status_badge = StatusBadge(status=status)
        info_layout.addWidget(self.status_badge)
        desc_layout.addLayout(info_layout, 1)

        self.add_layout(desc_layout)

        # 操作按钮
        btn_layout = QHBoxLayout()
        self.toggle_btn = create_button("启用", style="primary")
        self.config_btn = create_button("配置")
        btn_layout.addWidget(self.toggle_btn)
        btn_layout.addWidget(self.config_btn)
        btn_layout.addStretch()
        self.add_layout(btn_layout)

    def set_status(self, status: str):
        self._status = status
        self.status_badge.set_status(status)
        if status == "online":
            self.toggle_btn.setText("停用")
        else:
            self.toggle_btn.setText("启用")


class WorkflowPanel(QWidget):
    """工作流中心：展示和管理可用工作流模块."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        header = SectionHeader("🚀 工作流中心")
        layout.addWidget(header)

        desc = create_label(
            "管理和配置分子科学工作流模块。部分模块为预览版本，功能持续完善中。",
            level="caption",
        )
        layout.addWidget(desc)

        # 工作流网格
        grid = QWidget()
        grid_layout = QHBoxLayout(grid)
        grid_layout.setSpacing(12)

        workflows = [
            ("🧬", "分子生成", "基于 AI 的分子结构生成与优化", "offline"),
            ("🎯", "分子对接", "蛋白质-配体对接预测", "offline"),
            ("📊", "QSAR", "定量构效关系建模", "offline"),
            ("🌊", "分子动力学", "MD 模拟与分析", "offline"),
        ]

        for icon, name, desc_text, status in workflows:
            card = WorkflowCard(icon, name, desc_text, status)
            grid_layout.addWidget(card)

        layout.addWidget(grid)

        # 占位提示
        empty = EmptyStateWidget(
            icon="🔧",
            title="工作流模块开发中",
            subtitle="当前版本为占位界面，后续将接入实际计算引擎",
        )
        layout.addWidget(empty)
        layout.addStretch()
