"""Thread-safe utilities for Dear PyGui UI updates."""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable
from typing import TypeVar

import dearpygui.dearpygui as dpg

T = TypeVar("T")


def run_in_main(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator: ensure a function runs on the main thread.

    Dear PyGui is single-threaded for UI operations. This decorator
    queues the call if invoked from a background thread.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if threading.current_thread() is threading.main_thread():
            return func(*args, **kwargs)
        # Use dpg's task queue for cross-thread UI updates
        result = [None]
        event = threading.Event()

        def _task():
            result[0] = func(*args, **kwargs)
            event.set()

        dpg.split_frame(delay=1, callback=_task)
        event.wait(timeout=5)
        return result[0]

    return wrapper


def safe_set_value(tag: str, value) -> None:
    """Set a dpg item value only if it exists."""
    if dpg.does_item_exist(tag):
        dpg.set_value(tag, value)


def safe_configure(tag: str, **kwargs) -> None:
    """Configure a dpg item only if it exists."""
    if dpg.does_item_exist(tag):
        dpg.configure_item(tag, **kwargs)


def safe_show(tag: str) -> None:
    """Show a dpg item only if it exists."""
    if dpg.does_item_exist(tag):
        dpg.show_item(tag)


def safe_hide(tag: str) -> None:
    """Hide a dpg item only if it exists."""
    if dpg.does_item_exist(tag):
        dpg.hide_item(tag)


def safe_delete(tag: str) -> None:
    """Delete a dpg item only if it exists."""
    if dpg.does_item_exist(tag):
        dpg.delete_item(tag)


def clear_container(tag: str) -> None:
    """Remove all children from a container."""
    children = dpg.get_item_children(tag, 1) or []
    for child in children:
        dpg.delete_item(child)
