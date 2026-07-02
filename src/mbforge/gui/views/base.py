"""Base view class."""

from __future__ import annotations

from typing import TYPE_CHECKING

import dearpygui.dearpygui as dpg

if TYPE_CHECKING:
    from ..app import MBForgeApp


class BaseView:
    """Abstract base class for all views."""

    view_name: str = ""

    def __init__(self, app: MBForgeApp):
        self.app = app
        self.state = app.state
        self.api = app.api
        self.parent_tag = ""
        self._container_tag = ""

    def create(self, parent_tag: str):
        """Create the view UI inside the given parent container."""
        self.parent_tag = parent_tag
        self._container_tag = f"view_{self.view_name}"
        with dpg.group(parent=parent_tag, tag=self._container_tag, show=False):
            self._build()

    def _build(self):
        """Override in subclasses to build the view UI."""
        raise NotImplementedError

    def show(self):
        """Show this view."""
        if dpg.does_item_exist(self._container_tag):
            dpg.show_item(self._container_tag)

    def hide(self):
        """Hide this view."""
        if dpg.does_item_exist(self._container_tag):
            dpg.hide_item(self._container_tag)

    def refresh(self):
        """Refresh view data. Override in subclasses."""
        pass
