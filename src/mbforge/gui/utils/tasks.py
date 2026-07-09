"""Background task utilities for MBForge GUI."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TypeVar

from ...utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def run_in_background(
    func: Callable[..., T],
    *args,
    on_success: Callable[[T], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
    daemon: bool = True,
) -> threading.Thread:
    """Run a function in a background thread with optional callbacks.

    Args:
        func: Function to run.
        *args: Arguments to pass to func.
        on_success: Called with func's return value on success.
        on_error: Called with the exception on failure.
        daemon: Whether the thread is a daemon thread.

    Returns:
        The started thread.
    """
    def _worker():
        try:
            result = func(*args)
            if on_success:
                on_success(result)
        except Exception as e:
            logger.error("Background task failed: %s", e)
            if on_error:
                on_error(e)

    thread = threading.Thread(target=_worker, daemon=daemon)
    thread.start()
    return thread


def run_with_refresh(
    func: Callable[..., None],
    refresh: Callable[[], None],
    *args,
    daemon: bool = True,
) -> threading.Thread:
    """Run a function and call refresh() on success.

    Common pattern: execute API call, then refresh the view.

    Args:
        func: Function to run (should not call refresh).
        refresh: View refresh function to call on success.
        *args: Arguments to pass to func.
        daemon: Whether the thread is a daemon thread.

    Returns:
        The started thread.
    """
    def _worker():
        try:
            func(*args)
            refresh()
        except Exception as e:
            logger.error("Background task failed: %s", e)

    thread = threading.Thread(target=_worker, daemon=daemon)
    thread.start()
    return thread
