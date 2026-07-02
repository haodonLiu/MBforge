"""Reusable filter/tab bar component."""

from __future__ import annotations

from typing import Any, Callable

import dearpygui.dearpygui as dpg

from ..utils.i18n import t


def filter_bar(
    options: list[str],
    callback: Callable[[int, Any, str], None],
    active: str = "",
    prefix: str = "",
    button_width: int = 80,
    parent: str | None = None,
) -> None:
    """Create a horizontal filter/tab bar.

    Args:
        options: List of filter option keys (e.g., ["all", "pending", "done"]).
        callback: Callback with user_data set to the option key.
        active: Currently active option (gets accent theme).
        prefix: i18n prefix for button labels (e.g., "queue." → "queue.all").
        button_width: Width of each button.
        parent: Parent container tag.
    """
    kwargs = {}
    if parent:
        kwargs["parent"] = parent

    with dpg.group(horizontal=True, **kwargs):
        for option in options:
            label_key = f"{prefix}{option}" if prefix else option
            btn = dpg.add_button(
                label=t(label_key),
                width=button_width,
                height=28,
                callback=callback,
                user_data=option,
            )
            if option == active:
                dpg.bind_item_theme(btn, "accent_button")
            dpg.add_spacer(width=4)
