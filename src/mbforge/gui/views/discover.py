"""Discover view — knowledge base search and AI agent chat."""

from __future__ import annotations

from typing import Any

import dearpygui.dearpygui as dpg

from ...utils.logger import get_logger
from ..api.sse import SSEClient
from ..components import search_bar
from ..utils import (
    COLOR_ASSISTANT,
    COLOR_ERROR,
    COLOR_TEXT_DIM,
    COLOR_TEXT_MUTED,
    COLOR_USER,
    clear_container,
    run_in_background,
    t,
)
from .base import BaseView

logger = get_logger(__name__)


class DiscoverView(BaseView):
    """Search and AI chat view."""

    view_name = "discover"

    def __init__(self, app):
        super().__init__(app)
        self.sse = SSEClient(app.state.base_url)
        self._results: list[dict] = []
        self._chat_messages: list[dict] = []
        self._session_id = ""
        self._current_tab = "search"
        self._streaming = False

    def _build(self) -> None:
        dpg.add_spacer(height=12)

        # Tab bar
        with dpg.group(horizontal=True):
            search_btn = dpg.add_button(
                label=t("discover.search"),
                tag="discover_tab_search",
                width=100,
                height=32,
                callback=self._on_tab_click,
                user_data="search",
            )
            dpg.bind_item_theme(search_btn, "accent_button")
            dpg.add_button(
                label=t("discover.chat"),
                tag="discover_tab_chat",
                width=100,
                height=32,
                callback=self._on_tab_click,
                user_data="chat",
            )

        dpg.add_spacer(height=12)

        # Search panel
        with dpg.group(tag="discover_search_panel"):
            search_bar(
                input_tag="discover_search_input",
                callback=self._on_search,
                placeholder=t("discover.search_hint"),
            )

            dpg.add_spacer(height=12)
            dpg.add_child_window(
                tag="discover_results",
                width=700,
                height=500,
                border=True,
            )

        # Chat panel (hidden)
        with dpg.group(tag="discover_chat_panel", show=False):
            dpg.add_child_window(
                tag="discover_chat_messages",
                width=700,
                height=480,
                border=True,
            )
            dpg.add_spacer(height=8)
            search_bar(
                input_tag="discover_chat_input",
                callback=self._on_send_message,
                placeholder=t("discover.chat_hint"),
                button_label=t("discover.send"),
                input_width=600,
            )

    def _on_tab_click(self, sender: int, app_data: Any, user_data: str) -> None:
        self._switch_tab(user_data)

    def _switch_tab(self, tab: str) -> None:
        self._current_tab = tab

        for tab_name, btn_tag in [("search", "discover_tab_search"), ("chat", "discover_tab_chat")]:
            theme = "accent_button" if tab_name == tab else "sidebar_button"
            dpg.bind_item_theme(btn_tag, theme)

        if tab == "search":
            dpg.show_item("discover_search_panel")
            dpg.hide_item("discover_chat_panel")
        else:
            dpg.hide_item("discover_search_panel")
            dpg.show_item("discover_chat_panel")
            if not self._session_id:
                self._init_chat()

    def _on_search(self, sender: int, app_data: Any, user_data: Any) -> None:
        query = dpg.get_value("discover_search_input")
        if not query or not self.state.library_root:
            return

        self._results = []
        self._render_results([], loading=True)

        def on_results(results):
            self._results.extend(results)
            self._render_results(self._results)

        def on_error(error):
            self._render_results([], error=error)

        self.sse.stream_search(
            query=query,
            library_root=self.state.library_root,
            on_results=on_results,
            on_done=lambda total: None,
            on_error=on_error,
        )

    def _render_results(self, results: list[dict], loading: bool = False, error: str = "") -> None:
        clear_container("discover_results")

        if loading:
            dpg.add_text(t("common.loading"), parent="discover_results", color=COLOR_TEXT_DIM)
            return

        if error:
            dpg.add_text(f"{t('common.error')}: {error}", parent="discover_results", color=COLOR_ERROR)
            return

        if not results:
            dpg.add_text(t("discover.no_results"), parent="discover_results", color=COLOR_TEXT_MUTED)
            return

        for i, result in enumerate(results):
            with dpg.group(parent="discover_results"):
                with dpg.group(horizontal=True):
                    dpg.add_text(f"#{i + 1}", color=COLOR_USER)
                    dpg.add_spacer(width=8)
                    dpg.add_text(f"Score: {result.get('score', 0):.2f}", color=COLOR_TEXT_DIM)
                    doc_id = result.get("doc_id", "")
                    if doc_id:
                        dpg.add_spacer(width=12)
                        dpg.add_text(doc_id, color=COLOR_TEXT_MUTED)
                    page = result.get("page", 0)
                    if page:
                        dpg.add_spacer(width=8)
                        dpg.add_text(f"p.{page}", color=COLOR_TEXT_MUTED)

                dpg.add_text(result.get("text", ""), wrap=680, color=(200, 200, 210))
                dpg.add_separator()
                dpg.add_spacer(height=4)

    def _init_chat(self) -> None:
        if not self.state.library_root:
            return

        run_in_background(
            self.api.agent_create_session,
            self.state.library_root,
            on_success=lambda sid: setattr(self, "_session_id", sid),
            on_error=lambda e: logger.error("Failed to create agent session: %s", e),
        )

    def _on_send_message(self, sender: int, app_data: Any, user_data: Any) -> None:
        message = dpg.get_value("discover_chat_input")
        if not message or self._streaming:
            return

        dpg.set_value("discover_chat_input", "")
        self._chat_messages.append({"role": "user", "content": message})
        self._render_chat()

        self._streaming = True
        assistant_content = ""

        def on_chunk(delta):
            nonlocal assistant_content
            assistant_content += delta
            if self._chat_messages and self._chat_messages[-1].get("role") == "assistant_streaming":
                self._chat_messages[-1]["content"] = assistant_content
            else:
                self._chat_messages.append({"role": "assistant_streaming", "content": assistant_content})
            self._render_chat()

        def on_done():
            self._streaming = False
            for msg in self._chat_messages:
                if msg.get("role") == "assistant_streaming":
                    msg["role"] = "assistant"
            self._render_chat()

        def on_error(error):
            self._streaming = False
            self._chat_messages.append({"role": "assistant", "content": f"[Error: {error}]"})
            self._render_chat()

        self.sse.stream_chat(
            session_id=self._session_id,
            user_input=message,
            on_chunk=on_chunk,
            on_tool_call=lambda tool: logger.info("Agent tool call: %s", tool),
            on_done=on_done,
            on_error=on_error,
        )

    def _render_chat(self) -> None:
        clear_container("discover_chat_messages")

        for msg in self._chat_messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                color = COLOR_USER
                prefix = "You: "
            else:
                color = COLOR_ASSISTANT
                prefix = "AI: "

            with dpg.group(parent="discover_chat_messages"):
                dpg.add_text(prefix, color=color, wrap=680)
                dpg.add_text(content, color=COLOR_TEXT_DIM, wrap=680)
                dpg.add_spacer(height=8)

    def refresh(self) -> None:
        pass
