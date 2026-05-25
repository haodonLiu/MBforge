"""UI dialogs sub-package."""

from __future__ import annotations

from .dialogs import NewProjectDialog, SettingsDialog
from .unidock_dialog import UniDockConfigDialog

__all__ = [
    "NewProjectDialog",
    "SettingsDialog",
    "UniDockConfigDialog",
]
