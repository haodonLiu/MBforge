"""Workspace view — file tree, dashboard, and document viewer."""

from __future__ import annotations

from typing import Any

import dearpygui.dearpygui as dpg

from ...utils.logger import get_logger
from ..components import stat_card
from ..utils import (
    clear_container,
    get_status_color,
    run_with_refresh,
    safe_set_value,
    t,
)
from ..utils.constants import FILE_TREE_WIDTH
from .base import BaseView

logger = get_logger(__name__)


class WorkspaceView(BaseView):
    """Main workspace with file tree and dashboard."""

    view_name = "workspace"

    def __init__(self, app):
        super().__init__(app)
        self._docs: list = []

    def _build(self) -> None:
        with dpg.group(horizontal=True):
            self._build_file_tree_panel()
            with dpg.group():
                dpg.add_spacer(height=8)
                self._build_dashboard()
                dpg.add_spacer(height=8)
                self._build_document_list()

    def _build_file_tree_panel(self) -> None:
        with dpg.child_window(
            tag="workspace_filetree_panel",
            width=FILE_TREE_WIDTH,
            autosize_y=True,
            border=True,
            no_scrollbar=False,
        ):
            dpg.add_text(t("workspace.file_tree"), color=(180, 180, 190))
            dpg.add_spacer(height=4)
            dpg.add_child_window(
                tag="workspace_filetree",
                autosize_x=True,
                autosize_y=True,
                border=False,
            )

    def _build_dashboard(self) -> None:
        with dpg.group(tag="workspace_dashboard"):
            with dpg.group(horizontal=True):
                stat_card(t("workspace.documents"), "0", "stat_docs")
                dpg.add_spacer(width=12)
                stat_card(t("workspace.sections"), "0", "stat_sections")
                dpg.add_spacer(width=12)
                stat_card(t("workspace.indexed"), "0", "stat_indexed")
                dpg.add_spacer(width=12)
                stat_card(t("workspace.molecules"), "0", "stat_mols")

            dpg.add_spacer(height=12)

            with dpg.group(horizontal=True):
                sync_btn = dpg.add_button(
                    label=t("workspace.sync"),
                    tag="workspace_sync_btn",
                    width=100,
                    height=32,
                    callback=self._on_sync,
                )
                dpg.bind_item_theme(sync_btn, "accent_button")
                dpg.add_spacer(width=8)
                dpg.add_button(
                    label=t("workspace.scan"),
                    tag="workspace_scan_btn",
                    width=100,
                    height=32,
                    callback=self._on_scan,
                )

    def _build_document_list(self) -> None:
        dpg.add_text(t("workspace.documents"), color=(180, 180, 190))
        dpg.add_spacer(height=4)
        dpg.add_child_window(
            tag="workspace_doclist",
            width=600,
            height=300,
            border=True,
        )

    def refresh(self) -> None:
        if not self.state.library_root:
            return
        run_with_refresh(self._load_docs, self._render_docs, self.state.library_root)

    def _load_docs(self, root: str) -> None:
        docs = self.api.list_documents(root)
        self._docs = docs
        self.state.doc_count = len(docs)
        safe_set_value("stat_docs", str(len(docs)))

    def _render_docs(self) -> None:
        clear_container("workspace_doclist")
        for doc in self._docs:
            with dpg.group(parent="workspace_doclist", horizontal=True):
                dpg.add_text(doc.file_name or doc.doc_id, color=(200, 200, 210))
                dpg.add_spacer(width=8)
                dpg.add_text(doc.status, color=get_status_color(doc.status))

    def _on_sync(self, sender: int, app_data: Any, user_data: Any) -> None:
        if not self.state.library_root:
            return
        run_with_refresh(
            self.api.enqueue_documents,
            self.refresh,
            self.state.library_root,
        )

    def _on_scan(self, sender: int, app_data: Any, user_data: Any) -> None:
        if not self.state.library_root:
            return
        run_with_refresh(
            self.api.scan_files,
            self.refresh,
            self.state.library_root,
        )
