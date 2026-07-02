"""Reusable search bar component."""

from __future__ import annotations

from typing import Any, Callable

import dearpygui.dearpygui as dpg

from ..utils.i18n import t


def search_bar(
    input_tag: str,
    callback: Callable[[int, Any, Any], None],
    placeholder: str = "",
    input_width: int = 500,
    button_label: str = "",
    button_width: int = 80,
    parent: str | None = None,
) -> None:
    """Create a search bar with input and button.

    Args:
        input_tag: Tag for the input text element.
        callback: Callback for search action (button click or Enter).
        placeholder: Input placeholder text.
        input_width: Width of the input field.
        button_label: Button text. Defaults to i18n "discover.search".
        button_width: Width of the button.
        parent: Parent container tag.
    """
    if not button_label:
        button_label = t("discover.search")
    if not placeholder:
        placeholder = t("discover.search_hint")

    kwargs = {}
    if parent:
        kwargs["parent"] = parent

    with dpg.group(horizontal=True, **kwargs):
        dpg.add_input_text(
            tag=input_tag,
            width=input_width,
            height=36,
            hint=placeholder,
            on_enter=True,
            callback=callback,
        )
        btn = dpg.add_button(
            label=button_label,
            width=button_width,
            height=36,
            callback=callback,
        )
        dpg.bind_item_theme(btn, "accent_button")
