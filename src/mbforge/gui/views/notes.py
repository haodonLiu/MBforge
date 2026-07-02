"""Notes view — note editor with wiki-links."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import dearpygui.dearpygui as dpg

from ..api.models import NoteEntry
from ..components import two_panel
from ..utils import (
    t,
    run_in_background,
    safe_set_value,
    clear_container,
)
from .base import BaseView

from ...utils.logger import get_logger

logger = get_logger(__name__)


class NotesView(BaseView):
    """Notes editor view."""

    view_name = "notes"

    def __init__(self, app):
        super().__init__(app)
        self._notes: list[dict] = []
        self._current_note_id: str | None = None

    def _build(self) -> None:
        two_panel(
            left_tag="notes_left_panel",
            right_tag="notes_right_panel",
            left_width=240,
            left_builder=self._build_note_list,
            right_builder=self._build_editor,
        )

    def _build_note_list(self) -> None:
        with dpg.group(horizontal=True):
            dpg.add_text(t("notes.title"), color=(180, 180, 190))
            dpg.add_spacer(width=0)
            new_btn = dpg.add_button(
                label="+",
                width=28,
                height=28,
                callback=self._on_new_note,
            )
            dpg.bind_item_theme(new_btn, "accent_button")

        dpg.add_spacer(height=8)
        dpg.add_input_text(
            tag="notes_search",
            width=224,
            height=28,
            hint=t("notes.search"),
            callback=self._on_search,
        )
        dpg.add_spacer(height=8)
        dpg.add_child_window(
            tag="notes_list",
            width=224,
            height=500,
            border=False,
        )

    def _build_editor(self) -> None:
        with dpg.group(tag="notes_editor"):
            dpg.add_input_text(
                tag="note_title_input",
                width=500,
                height=32,
                hint="Note title...",
            )
            dpg.add_spacer(height=8)
            dpg.add_input_text(
                tag="note_content_input",
                width=600,
                height=400,
                multiline=True,
                hint="Write your note here... Use [[wiki-links]] to link to other notes.",
            )
            dpg.add_spacer(height=12)
            with dpg.group(horizontal=True):
                save_btn = dpg.add_button(
                    label=t("settings.save"),
                    width=80,
                    height=32,
                    callback=self._on_save,
                )
                dpg.bind_item_theme(save_btn, "accent_button")
                dpg.add_spacer(width=8)
                dpg.add_button(
                    label=t("queue.delete"),
                    width=80,
                    height=32,
                    callback=self._on_delete,
                )
            dpg.add_spacer(height=12)
            dpg.add_text(t("notes.backlinks"), color=(140, 140, 150))
            dpg.add_child_window(
                tag="notes_backlinks",
                width=600,
                height=100,
                border=True,
            )

    def refresh(self) -> None:
        if not self.state.project_root:
            return
        self._load_notes()

    def _load_notes(self) -> None:
        def _worker():
            try:
                notes = self.api.list_notes(self.state.project_root)
                self._notes = [self._note_to_dict(n) for n in notes]
                self._render_list()
            except Exception as e:
                logger.error("Failed to load notes: %s", e)

        run_in_background(_worker)

    def _note_to_dict(self, note: NoteEntry) -> dict:
        return {
            "id": note.id,
            "title": note.title,
            "tags": note.tags,
            "created_at": note.created_at,
        }

    def _render_list(self) -> None:
        clear_container("notes_list")

        if not self._notes:
            dpg.add_text(t("notes.no_notes"), parent="notes_list", color=(100, 100, 110))
            return

        for note in self._notes:
            with dpg.group(parent="notes_list", horizontal=True):
                title = note.get("title", "Untitled")
                dpg.add_button(
                    label=title,
                    callback=self._on_select_note,
                    user_data=note["id"],
                    small=True,
                )
            dpg.add_spacer(height=2)

    def _on_select_note(self, sender: int, app_data: Any, user_data: str) -> None:
        note_id = user_data
        self._current_note_id = note_id

        def _worker():
            try:
                content = self.api.get_note(self.state.project_root, note_id)
                title = next((n["title"] for n in self._notes if n["id"] == note_id), "")
                safe_set_value("note_title_input", title)
                safe_set_value("note_content_input", content)
            except Exception as e:
                logger.error("Failed to load note: %s", e)

        run_in_background(_worker)

    def _on_new_note(self, sender: int, app_data: Any, user_data: Any) -> None:
        note_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        title = f"New Note {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        def _worker():
            try:
                entry = NoteEntry(id=note_id, title=title, content="", created_at=now, updated_at=now)
                self.api.save_note(self.state.project_root, entry)
                self.refresh()
                self._on_select_note(None, 0, note_id)
            except Exception as e:
                logger.error("Failed to create note: %s", e)

        run_in_background(_worker)

    def _on_save(self, sender: int, app_data: Any, user_data: Any) -> None:
        if not self._current_note_id or not self.state.project_root:
            return

        title = dpg.get_value("note_title_input")
        content = dpg.get_value("note_content_input")
        now = datetime.now(timezone.utc).isoformat()

        def _worker():
            try:
                entry = NoteEntry(id=self._current_note_id, title=title, content=content, created_at=now, updated_at=now)
                self.api.save_note(self.state.project_root, entry)
                self.refresh()
            except Exception as e:
                logger.error("Failed to save note: %s", e)

        run_in_background(_worker)

    def _on_delete(self, sender: int, app_data: Any, user_data: Any) -> None:
        if not self._current_note_id or not self.state.project_root:
            return

        def _worker():
            try:
                self.api.delete_note(self.state.project_root, self._current_note_id)
                self._current_note_id = None
                safe_set_value("note_title_input", "")
                safe_set_value("note_content_input", "")
                self.refresh()
            except Exception as e:
                logger.error("Failed to delete note: %s", e)

        run_in_background(_worker)

    def _on_search(self, sender: int, app_data: Any, user_data: Any) -> None:
        query = dpg.get_value("notes_search")
        if not query:
            self._render_list()
            return

        filtered = [n for n in self._notes if query.lower() in n.get("title", "").lower()]
        original = self._notes
        self._notes = filtered
        self._render_list()
        self._notes = original
