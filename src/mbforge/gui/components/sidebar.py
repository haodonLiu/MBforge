"""Navigation sidebar component."""

from __future__ import annotations

from typing import Any, Callable

import dearpygui.dearpygui as dpg

from ..utils.constants import SIDEBAR_WIDTH
from ..utils.i18n import t

# Navigation items: (view_name, icon_char, i18n_key)
_PRIMARY_NAV = [
    ("workspace", "\u2302", "nav.workspace"),
    ("discover", "\u26B2", "nav.discover"),
    ("molecules", "\u2697", "nav.molecules"),
]

_SECONDARY_NAV = [
    ("queue", "\u21BB", "nav.queue"),
    ("notes", "\u270E", "nav.notes"),
]

_BOTTOM_NAV = [
    ("settings", "\u2699", "nav.settings"),
]


class Sidebar:
    """Vertical icon sidebar for navigation.

    Renders a 56px-wide rail with icon buttons grouped into
    primary, secondary, and bottom sections.
    """

    def __init__(self, on_navigate: Callable[[str], None]):
        self._on_navigate = on_navigate
        self._active_view = "workspace"
        self._buttons: dict[str, str] = {}  # view_name → button_tag

    def create(self, parent_tag: str) -> None:
        """Create the sidebar in the given parent container."""
        with dpg.child_window(
            tag="sidebar",
            parent=parent_tag,
            width=SIDEBAR_WIDTH,
            autosize_y=True,
            no_scrollbar=True,
            border=False,
        ):
            # Logo
            dpg.add_spacer(height=8)
            dpg.add_text("MB", color=(88, 166, 255))
            dpg.add_spacer(height=16)

            # Primary nav
            for view_name, icon, i18n_key in _PRIMARY_NAV:
                self._add_button(view_name, icon, i18n_key)
            dpg.add_spacer(height=8)

            # Secondary nav
            for view_name, icon, i18n_key in _SECONDARY_NAV:
                self._add_button(view_name, icon, i18n_key)

            # Spacer pushes remaining items to bottom
            dpg.add_spacer(height=0, tag="sidebar_spacer")

            # Bottom nav
            for view_name, icon, i18n_key in _BOTTOM_NAV:
                self._add_button(view_name, icon, i18n_key)
            dpg.add_spacer(height=8)

    def _add_button(self, view_name: str, icon: str, i18n_key: str) -> None:
        tag = f"nav_btn_{view_name}"
        self._buttons[view_name] = tag
        btn = dpg.add_button(
            label=icon,
            tag=tag,
            width=SIDEBAR_WIDTH - 8,
            height=40,
            callback=self._on_click,
            user_data=view_name,
        )
        dpg.bind_item_theme(btn, "sidebar_button")
        with dpg.tooltip(tag):
            dpg.add_text(t(i18n_key))

    def _on_click(self, sender: int, app_data: Any, user_data: str) -> None:
        view_name = user_data
        self.set_active(view_name)
        self._on_navigate(view_name)

    def set_active(self, view_name: str) -> None:
        """Update active state visual."""
        # Reset previous button
        if self._active_view in self._buttons:
            prev_tag = self._buttons[self._active_view]
            if dpg.does_item_exist(prev_tag):
                dpg.bind_item_theme(prev_tag, "sidebar_button")

        self._active_view = view_name

        # Highlight new button
        if view_name in self._buttons:
            tag = self._buttons[view_name]
            if dpg.does_item_exist(tag):
                dpg.bind_item_theme(tag, "sidebar_button_active")
