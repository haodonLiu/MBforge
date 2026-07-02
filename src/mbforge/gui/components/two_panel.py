"""Reusable two-panel layout component."""

from __future__ import annotations

from collections.abc import Callable

import dearpygui.dearpygui as dpg


def two_panel(
    left_tag: str,
    right_tag: str,
    left_width: int = 240,
    gap: int = 16,
    parent: str | None = None,
    left_builder: Callable[[], None] | None = None,
    right_builder: Callable[[], None] | None = None,
) -> None:
    """Create a two-panel horizontal layout.

    Args:
        left_tag: Tag for the left panel group.
        right_tag: Tag for the right panel group.
        left_width: Width of the left panel. Use -1 for auto.
        gap: Gap between panels in pixels.
        parent: Parent container tag.
        left_builder: Optional callable to build left panel content.
        right_builder: Optional callable to build right panel content.
    """
    kwargs = {}
    if parent:
        kwargs["parent"] = parent

    with dpg.group(horizontal=True, **kwargs):
        # Left panel
        left_kwargs = {"tag": left_tag}
        if left_width > 0:
            left_kwargs["width"] = left_width
        with dpg.group(**left_kwargs):
            if left_builder:
                left_builder()

        dpg.add_spacer(width=gap)

        # Right panel
        with dpg.group(tag=right_tag, width=-1):
            if right_builder:
                right_builder()
