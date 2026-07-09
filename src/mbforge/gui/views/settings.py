"""Settings view — application configuration."""

from __future__ import annotations

from threading import Thread
from typing import Any

import dearpygui.dearpygui as dpg

from ...utils.logger import get_logger
from ..utils.i18n import get_language, set_language, t
from ..utils.threading import clear_container
from .base import BaseView

logger = get_logger(__name__)


class SettingsView(BaseView):
    """Settings view with tabs."""

    view_name = "settings"

    def __init__(self, app):
        super().__init__(app)
        self._settings: dict = {}
        self._current_tab = "general"

    def _build(self) -> None:
        dpg.add_spacer(height=12)

        # Tab buttons
        with dpg.group(horizontal=True):
            tabs = [
                ("general", t("settings.general")),
                ("ai_models", t("settings.ai_models")),
                ("pdf_processing", t("settings.pdf_processing")),
                ("models", t("settings.models")),
                ("system", t("settings.system")),
                ("cache", t("settings.cache")),
                ("about", t("settings.about")),
            ]
            for tab_key, tab_label in tabs:
                btn = dpg.add_button(
                    label=tab_label,
                    width=100,
                    height=28,
                    callback=self._on_tab_click,
                    user_data=tab_key,
                )
                if tab_key == "general":
                    dpg.bind_item_theme(btn, "accent_button")
                dpg.add_spacer(width=4)

        dpg.add_spacer(height=16)

        # Tab content
        dpg.add_child_window(
            tag="settings_content",
            width=700,
            height=450,
            border=True,
        )
        self._build_general_tab()

        dpg.add_spacer(height=16)

        # Action buttons
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
                label=t("settings.cancel"),
                width=80,
                height=32,
                callback=self._on_cancel,
            )

    def _on_tab_click(self, sender: int, app_data: Any, user_data: str) -> None:
        self._switch_tab(user_data)

    def _switch_tab(self, tab: str) -> None:
        self._current_tab = tab
        clear_container("settings_content")

        builders = {
            "general": self._build_general_tab,
            "ai_models": self._build_ai_models_tab,
            "about": self._build_about_tab,
        }

        builder = builders.get(tab)
        if builder:
            builder()
        else:
            dpg.add_text(f"Tab: {tab}", parent="settings_content", color=(140, 140, 150))

    def _build_general_tab(self) -> None:
        container = "settings_content"
        dpg.add_text(t("settings.general"), parent=container, color=(200, 200, 210))
        dpg.add_spacer(parent=container, height=12)

        with dpg.group(parent=container, horizontal=True):
            dpg.add_text(t("settings.language"), color=(180, 180, 190))
            dpg.add_spacer(width=12)
            dpg.add_combo(
                ("zh-CN", "en"),
                default_value=get_language(),
                tag="settings_language",
                width=120,
            )

        dpg.add_spacer(parent=container, height=12)

        with dpg.group(parent=container, horizontal=True):
            dpg.add_text(t("settings.theme"), color=(180, 180, 190))
            dpg.add_spacer(width=12)
            dpg.add_combo(
                (t("settings.dark"), t("settings.light")),
                default_value=t("settings.dark"),
                tag="settings_theme",
                width=120,
            )

    def _build_ai_models_tab(self) -> None:
        container = "settings_content"
        dpg.add_text(t("settings.ai_models"), parent=container, color=(200, 200, 210))
        dpg.add_spacer(parent=container, height=12)

        with dpg.group(parent=container):
            dpg.add_text("LLM Provider", color=(180, 180, 190))
            dpg.add_input_text(
                tag="settings_llm_provider",
                default_value=self._settings.get("llm_provider", ""),
                width=300,
                hint="e.g., openai, anthropic",
            )
            dpg.add_spacer(height=8)
            dpg.add_text("API Key", color=(180, 180, 190))
            dpg.add_input_text(
                tag="settings_llm_api_key",
                default_value="",
                width=300,
                password=True,
                hint="Enter API key",
            )
            dpg.add_spacer(height=8)
            dpg.add_text("Model", color=(180, 180, 190))
            dpg.add_input_text(
                tag="settings_llm_model",
                default_value=self._settings.get("llm_model", ""),
                width=300,
                hint="e.g., gpt-4, claude-3",
            )

    def _build_about_tab(self) -> None:
        container = "settings_content"
        dpg.add_text("MBForge", parent=container, color=(88, 166, 255))
        dpg.add_spacer(parent=container, height=4)
        dpg.add_text("v0.4.0", parent=container, color=(140, 140, 150))
        dpg.add_spacer(parent=container, height=12)
        dpg.add_text(
            "Molecular Knowledge Base & AI Workbench",
            parent=container,
            color=(180, 180, 190),
        )
        dpg.add_spacer(parent=container, height=12)
        dpg.add_text("License: CC BY-NC-SA 4.0", parent=container, color=(140, 140, 150))

    def refresh(self) -> None:
        Thread(target=self._load_settings, daemon=True).start()

    def _load_settings(self) -> None:
        try:
            self._settings = self.api.get_settings()
            lang = self._settings.get("language", "zh-CN")
            if dpg.does_item_exist("settings_language"):
                dpg.set_value("settings_language", lang)
        except Exception as e:
            logger.error("Failed to load settings: %s", e)

    def _on_save(self, sender: int, app_data: Any, user_data: Any) -> None:
        def _worker():
            try:
                settings = {}
                if dpg.does_item_exist("settings_language"):
                    settings["language"] = dpg.get_value("settings_language")
                    set_language(settings["language"])
                self.api.save_settings(settings)
            except Exception as e:
                logger.error("Failed to save settings: %s", e)

        Thread(target=_worker, daemon=True).start()

    def _on_cancel(self, sender: int, app_data: Any, user_data: Any) -> None:
        self.refresh()
