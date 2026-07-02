"""Reusable stat card and stat pill components."""

from __future__ import annotations

import dearpygui.dearpygui as dpg

from ..utils.colors import COLOR_TEXT, COLOR_TEXT_DIM


def stat_card(label: str, value: str, tag: str, parent: str | None = None) -> None:
    """Create a stat card with value and label.

    Args:
        label: Description text (e.g., "Documents").
        value: Display value (e.g., "42").
        tag: Unique tag for the value text element.
        parent: Parent container tag.
    """
    kwargs = {"tag": f"{tag}_group"}
    if parent:
        kwargs["parent"] = parent

    with dpg.group(**kwargs):
        dpg.add_text(value, tag=tag, color=COLOR_TEXT)
        dpg.add_text(label, color=COLOR_TEXT_DIM)


def stat_pill(label: str, value: str, tag: str, color: tuple, parent: str | None = None) -> None:
    """Create a compact stat pill with label and colored value.

    Args:
        label: Description text (e.g., "Pending").
        value: Display value (e.g., "5").
        tag: Unique tag for the value text element.
        color: RGB tuple for the value color.
        parent: Parent container tag.
    """
    kwargs = {}
    if parent:
        kwargs["parent"] = parent

    with dpg.group(horizontal=True, **kwargs):
        dpg.add_text(f"{label}: ", color=COLOR_TEXT_DIM)
        dpg.add_text(value, tag=tag, color=color)
