"""Toast notification component."""

from __future__ import annotations

import threading
import time
from typing import Callable

import dearpygui.dearpygui as dpg


class ToastManager:
    """Manages toast notifications with auto-dismiss.

    Toasts stack from the top-right corner and auto-dismiss
    after a configurable duration.
    """

    def __init__(self):
        self._counter = 0
        self._active_toasts: list[str] = []
        self._lock = threading.Lock()

    def create(self) -> None:
        """Create the toast container window."""
        dpg.add_window(
            tag="toast_container",
            pos=[0, 0],
            width=360,
            no_title_bar=True,
            no_move=True,
            no_resize=True,
            no_scrollbar=True,
            no_background=True,
            show=False,
        )

    def show(self, message: str, level: str = "info", duration: float = 3.0) -> None:
        """Show a toast notification.

        Args:
            message: Notification message text.
            level: 'info', 'success', 'warning', or 'error'.
            duration: Auto-dismiss duration in seconds.
        """
        with self._lock:
            self._counter += 1
            tag = f"toast_{self._counter}"
            self._active_toasts.append(tag)

        colors = {
            "info": (88, 166, 255),
            "success": (80, 200, 120),
            "warning": (250, 180, 50),
            "error": (240, 80, 80),
        }
        color = colors.get(level, colors["info"])

        # Calculate y position based on active toasts count
        with self._lock:
            y_pos = 12 + (len(self._active_toasts) - 1) * 52

        # Create toast theme
        theme_tag = f"{tag}_theme"
        with dpg.theme(tag=theme_tag):
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (32, 32, 38, 230))
                dpg.add_theme_color(dpg.mvThemeCol_Border, color)
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 8)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)

        # Create toast group
        with dpg.group(parent="toast_container", tag=tag, pos=[12, y_pos]):
            with dpg.child_window(
                width=340,
                height=44,
                border=True,
                no_scrollbar=True,
            ):
                dpg.bind_item_theme(dpg.last_item(), theme_tag)
                dpg.add_text(message, color=color, wrap=300)

        dpg.show_item("toast_container")

        # Auto-dismiss
        if duration > 0:
            threading.Timer(
                duration,
                self._dismiss,
                args=(tag,),
            ).start()

    def _dismiss(self, tag: str) -> None:
        """Dismiss a toast notification."""
        with self._lock:
            if tag in self._active_toasts:
                self._active_toasts.remove(tag)

        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        # Recalculate positions
        self._reposition_toasts()

        # Hide container if empty
        with self._lock:
            if not self._active_toasts:
                if dpg.does_item_exist("toast_container"):
                    dpg.hide_item("toast_container")

    def _reposition_toasts(self) -> None:
        """Reposition remaining toasts."""
        with self._lock:
            for i, tag in enumerate(self._active_toasts):
                if dpg.does_item_exist(tag):
                    dpg.set_item_pos(tag, [12, 12 + i * 52])


# Module-level singleton
_toast_manager: ToastManager | None = None


def set_toast_manager(manager: ToastManager) -> None:
    """Set the global toast manager instance."""
    global _toast_manager
    _toast_manager = manager


def show_toast(message: str, level: str = "info", duration: float = 3.0) -> None:
    """Show a toast notification using the global manager."""
    if _toast_manager:
        _toast_manager.show(message, level, duration)
