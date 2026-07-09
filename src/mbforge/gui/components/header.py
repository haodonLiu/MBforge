"""Header bar component."""

from __future__ import annotations

import dearpygui.dearpygui as dpg


class Header:
    """Top header bar with the active library name and actions."""

    def __init__(self):
        self.library_name = ""

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
            # Spacer to push library name to right
            dpg.add_spacer(width=0, tag="header_spacer")
            dpg.add_text(
                self.library_name,
                tag="header_project",
                color=(180, 180, 190),
            )
            dpg.add_spacer(width=12)

    def set_project(self, name: str):
        r"""Update the displayed library name (legacy method name kept for
        caller compatibility — see \`gui/app.py\`)."""
        self.library_name = name
        if dpg.does_item_exist("header_project"):
            dpg.set_value("header_project", name)
