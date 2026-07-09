"""Welcome view — project selection and creation."""

from __future__ import annotations

import os
from pathlib import Path

import dearpygui.dearpygui as dpg

from ..utils.i18n import t
from .base import BaseView


class WelcomeView(BaseView):
    """Welcome screen for project selection."""

    view_name = "welcome"

    def _build(self):
        # Center the content
        dpg.add_spacer(height=80)

        # Logo and title
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=0)
            dpg.add_text("MBForge", color=(88, 166, 255))
        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=0)
            dpg.add_text(
                t("welcome.subtitle"), color=(140, 140, 150)
            )

        dpg.add_spacer(height=40)

        # Action buttons
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=0)
            create_btn = dpg.add_button(
                label=t("welcome.create_project"),
                tag="welcome_create_btn",
                width=160,
                height=44,
                callback=self._on_create,
            )
            dpg.bind_item_theme(create_btn, "accent_button")
            dpg.add_spacer(width=16)
            dpg.add_button(
                label=t("welcome.open_project"),
                tag="welcome_open_btn",
                width=160,
                height=44,
                callback=self._on_open,
            )

        dpg.add_spacer(height=48)

        # Recent libraries
        dpg.add_text(t("welcome.recent_libraries"), color=(180, 180, 190))
        dpg.add_spacer(height=8)
        dpg.add_child_window(
            tag="welcome_recent_list",
            width=500,
            height=300,
            border=False,
            no_scrollbar=False,
        )

        dpg.add_spacer(height=20)

        # File dialog
        with dpg.file_dialog(
            directory_selector=True,
            show=False,
            callback=self._on_folder_selected,
            tag="welcome_folder_dialog",
            width=700,
            height=400,
            modal=True,
        ):
            dpg.add_file_extension(".pdf", color=(150, 255, 150, 255))
            dpg.add_file_extension(".md", color=(150, 150, 255, 255))

    def refresh(self):
        """Load recent libraries."""
        self._load_recent()

    def _load_recent(self):
        """Display recent libraries list."""
        container = "welcome_recent_list"
        # Clear existing children
        children = dpg.get_item_children(container, 1) or []
        for child in children:
            dpg.delete_item(child)

        recent = self.state.recent_libraries
        if not recent:
            dpg.add_text(
                t("welcome.no_libraries"),
                parent=container,
                color=(100, 100, 110),
            )
            return

        for proj in recent:
            name = proj.get("name", Path(proj.get("root", "")).name)
            root = proj.get("root", "")
            with dpg.group(parent=container, horizontal=True):
                dpg.add_button(
                    label=name,
                    callback=self._on_recent_click,
                    user_data=root,
                    small=True,
                )
                dpg.add_text(
                    root, color=(100, 100, 110)
                )

    def _on_create(self):
        """Open folder dialog to create new project."""
        dpg.show_item("welcome_folder_dialog")

    def _on_open(self):
        """Open folder dialog to open existing project."""
        dpg.show_item("welcome_folder_dialog")

    def _on_folder_selected(self, sender, app_data, user_data):
        """Handle folder selection."""
        folder = app_data.get("file_path", "")
        if not folder:
            return

        # Open project
        self.app.open_project(folder)

    def _on_recent_click(self, sender, app_data, user_data):
        """Handle recent project click."""
        root = user_data
        if os.path.isdir(root):
            self.app.open_project(root)
