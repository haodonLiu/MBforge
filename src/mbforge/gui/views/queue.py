"""Queue view — document processing queue."""

from __future__ import annotations

import threading
from typing import Any

import dearpygui.dearpygui as dpg

from ..components import stat_pill, filter_bar
from ..utils import (
    t,
    QUEUE_POLL_INTERVAL,
    get_status_color,
    run_with_refresh,
    safe_set_value,
    clear_container,
)
from .base import BaseView

from ...utils.logger import get_logger

logger = get_logger(__name__)


class QueueView(BaseView):
    """Processing queue view."""

    view_name = "queue"

    def __init__(self, app):
        super().__init__(app)
        self._tasks: list[dict] = []
        self._stats: dict[str, int] = {}
        self._filter = "all"
        self._polling = False
        self._poll_timer: threading.Timer | None = None
        self._poll_lock = threading.Lock()

    def _build(self) -> None:
        dpg.add_spacer(height=12)

        # Stats row
        with dpg.group(horizontal=True, tag="queue_stats"):
            stat_pill(t("queue.pending"), "0", "queue_stat_pending", (250, 180, 50))
            dpg.add_spacer(width=8)
            stat_pill(t("queue.processing"), "0", "queue_stat_processing", (88, 166, 255))
            dpg.add_spacer(width=8)
            stat_pill(t("queue.done"), "0", "queue_stat_done", (80, 200, 120))
            dpg.add_spacer(width=8)
            stat_pill(t("queue.failed"), "0", "queue_stat_failed", (240, 80, 80))

        dpg.add_spacer(height=12)

        # Filter buttons
        filter_bar(
            options=["all", "pending", "processing", "done", "failed"],
            callback=self._on_filter_click,
            active="all",
            prefix="queue.",
        )

        dpg.add_spacer(height=12)

        # Task list
        dpg.add_child_window(
            tag="queue_task_list",
            width=700,
            height=450,
            border=True,
        )

    def _on_filter_click(self, sender: int, app_data: Any, user_data: str) -> None:
        self._filter = user_data
        self._render_tasks()

    def refresh(self) -> None:
        if not self.state.project_root:
            return
        self._load_data()

    def _load_data(self) -> None:
        try:
            stats = self.api.get_queue_stats(self.state.project_root)
            self._stats = {
                "pending": stats.pending,
                "processing": stats.processing,
                "done": stats.done,
                "failed": stats.failed,
            }
            self._update_stats()

            tasks = self.api.get_queue(self.state.project_root)
            self._tasks = [self._task_to_dict(task) for task in tasks]
            self._render_tasks()
        except Exception as e:
            logger.error("Failed to load queue data: %s", e)

    def _task_to_dict(self, task) -> dict:
        return {
            "id": task.id,
            "file_path": task.file_path,
            "status": task.status,
            "stage": task.stage,
            "progress": task.progress,
            "error": task.error,
            "created_at": task.created_at,
        }

    def _update_stats(self) -> None:
        for key in ["pending", "processing", "done", "failed"]:
            safe_set_value(f"queue_stat_{key}", str(self._stats.get(key, 0)))

    def _render_tasks(self) -> None:
        clear_container("queue_task_list")

        filtered = self._tasks
        if self._filter != "all":
            filtered = [task for task in filtered if task.get("status") == self._filter]

        if not filtered:
            dpg.add_text(t("common.empty"), parent="queue_task_list", color=(100, 100, 110))
            return

        for task in filtered:
            self._render_task_row("queue_task_list", task)

    def _render_task_row(self, parent: str, task: dict) -> None:
        status = task.get("status", "pending")
        color = get_status_color(status)

        with dpg.group(parent=parent, horizontal=True):
            # File name
            file_path = task.get("file_path", "")
            file_name = file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            dpg.add_text(file_name, color=(200, 200, 210))
            dpg.add_spacer(width=12)

            # Status
            dpg.add_text(status, color=color)
            dpg.add_spacer(width=8)

            # Progress
            progress = task.get("progress", 0)
            if progress > 0:
                dpg.add_text(f"{progress:.0f}%", color=(140, 140, 150))

            dpg.add_spacer(width=0)

            # Actions
            task_id = task["id"]
            if status in ("pending", "processing"):
                dpg.add_button(
                    label=t("queue.cancel"),
                    width=60,
                    height=24,
                    callback=self._on_cancel,
                    user_data=task_id,
                    small=True,
                )
            if status == "failed":
                dpg.add_button(
                    label=t("queue.retry"),
                    width=60,
                    height=24,
                    callback=self._on_retry,
                    user_data=task_id,
                    small=True,
                )
            if status in ("done", "failed"):
                dpg.add_button(
                    label=t("queue.delete"),
                    width=60,
                    height=24,
                    callback=self._on_delete,
                    user_data=task_id,
                    small=True,
                )

        dpg.add_spacer(height=4)

    def _on_cancel(self, sender: int, app_data: Any, user_data: str) -> None:
        run_with_refresh(self.api.cancel_task, self.refresh, self.state.project_root, user_data)

    def _on_retry(self, sender: int, app_data: Any, user_data: str) -> None:
        run_with_refresh(self.api.retry_task, self.refresh, self.state.project_root, user_data)

    def _on_delete(self, sender: int, app_data: Any, user_data: str) -> None:
        run_with_refresh(self.api.delete_task, self.refresh, self.state.project_root, user_data)

    def start_polling(self) -> None:
        """Start polling for queue updates."""
        with self._poll_lock:
            if self._polling:
                return
            self._polling = True
        self._poll_once()

    def stop_polling(self) -> None:
        """Stop polling."""
        with self._poll_lock:
            self._polling = False
            if self._poll_timer:
                self._poll_timer.cancel()
                self._poll_timer = None

    def _poll_once(self) -> None:
        with self._poll_lock:
            if not self._polling:
                return

        self.refresh()

        with self._poll_lock:
            if self._polling:
                self._poll_timer = threading.Timer(
                    QUEUE_POLL_INTERVAL / 1000,
                    self._poll_once,
                )
                self._poll_timer.daemon = True
                self._poll_timer.start()
