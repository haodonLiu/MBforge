"""Header bar component."""

from __future__ import annotations

import dearpygui.dearpygui as dpg

from ..utils.i18n import t


class Header:
    """Top header bar with project name and actions."""

    def __init__(self):
        self.project_name = ""

    def create(self, parent_tag: str):
        """Create the header in the given parent container."""
        with dpg.group(parent=parent_tag, horizontal=True, tag="header"):
            dpg.add_spacer(width=12)
            dpg.add_text("MBForge", color=(88, 166, 255))
            dpg.add_spacer(width=8)
            dpg.add_text("-", color=(100, 100, 110))
            dpg.add_spacer(width=8)
            dpg.add_text(
                "Molecular Knowledge Base",
                color=(140, 140, 150),
                tag="header_subtitle",
            )
            # Spacer to push project name to right
            dpg.add_spacer(width=0, tag="header_spacer")
            dpg.add_text(
                self.project_name,
                tag="header_project",
                color=(180, 180, 190),
            )
            dpg.add_spacer(width=12)

    def set_project(self, name: str):
        """Update the displayed project name."""
        self.project_name = name
        if dpg.does_item_exist("header_project"):
            dpg.set_value("header_project", name)
