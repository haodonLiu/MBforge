"""MBForge UI 模块.

提供所有图形界面组件，包括主窗口、对话框、编辑器、预览等。
"""

from __future__ import annotations

from .chat_widget import ChatWidget
from .dialogs import MoleculeInfoDialog, NewProjectDialog, SettingsDialog
from .editor import MarkdownEditor
from .file_tree import FileTreeWidget
from .kb_panel import KnowledgeBasePanel
from .main_window import MainWindow
from .mol_panel import MoleculePanel
from .mol_renderer import MoleculeImageWidget, MoleculeRenderer
from .pdf_viewer import PDFViewer
from .preview import MarkdownPreview
from .status_dashboard import StatusDashboard
from .theme import (
    SearchBox,
    ThemeManager,
    create_button,
    create_input,
    create_label,
    create_table,
    create_tree,
)
from .todo_panel import TodoPanel
from .welcome_widget import WelcomeWidget
from .workflow_panel import WorkflowPanel

__all__ = [
    "ChatWidget",
    "NewProjectDialog",
    "SettingsDialog",
    "MoleculeInfoDialog",
    "MarkdownEditor",
    "FileTreeWidget",
    "KnowledgeBasePanel",
    "MainWindow",
    "MoleculePanel",
    "MoleculeImageWidget",
    "MoleculeRenderer",
    "PDFViewer",
    "MarkdownPreview",
    "StatusDashboard",
    "ThemeManager",
    "create_button",
    "create_input",
    "create_label",
    "create_table",
    "create_tree",
    "SearchBox",
    "TodoPanel",
    "WelcomeWidget",
    "WorkflowPanel",
]
