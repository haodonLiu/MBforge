"""Theme management for MBForge Dear PyGui frontend."""

from __future__ import annotations

import dearpygui.dearpygui as dpg

# ── Color Palettes ──────────────────────────────────────────


def _dark_palette() -> dict:
    return {
        "bg": (24, 24, 28),
        "bg_surface": (32, 32, 38),
        "bg_elevated": (40, 40, 46),
        "border": (55, 55, 62),
        "text": (230, 230, 235),
        "text_dim": (140, 140, 150),
        "accent": (88, 166, 255),
        "accent_hover": (110, 180, 255),
        "success": (80, 200, 120),
        "warning": (250, 180, 50),
        "error": (240, 80, 80),
        "button": (50, 50, 58),
        "button_hover": (62, 62, 72),
        "button_active": (70, 70, 82),
        "header": (38, 38, 44),
        "header_hover": (48, 48, 56),
        "selection": (50, 80, 120),
        "scrollbar": (45, 45, 52),
        "scrollbar_grab": (70, 70, 80),
    }


def _light_palette() -> dict:
    return {
        "bg": (245, 245, 248),
        "bg_surface": (255, 255, 255),
        "bg_elevated": (250, 250, 252),
        "border": (210, 210, 218),
        "text": (30, 30, 35),
        "text_dim": (120, 120, 130),
        "accent": (40, 120, 220),
        "accent_hover": (55, 140, 240),
        "success": (40, 160, 80),
        "warning": (200, 140, 20),
        "error": (200, 50, 50),
        "button": (230, 230, 236),
        "button_hover": (218, 218, 226),
        "button_active": (205, 205, 215),
        "header": (240, 240, 244),
        "header_hover": (228, 228, 234),
        "selection": (200, 220, 245),
        "scrollbar": (225, 225, 232),
        "scrollbar_grab": (195, 195, 205),
    }


# ── Theme Builders ──────────────────────────────────────────


def _build_base_theme(tag: str, c: dict) -> None:
    """Create the base application theme from a color palette."""
    with dpg.theme(tag=tag), dpg.theme_component(dpg.mvAll):
        # Backgrounds
        dpg.add_theme_color(dpg.mvThemeCol_WindowBg, c["bg"])
        dpg.add_theme_color(dpg.mvThemeCol_ChildBg, c["bg_surface"])
        dpg.add_theme_color(dpg.mvThemeCol_PopupBg, c["bg_elevated"])

        # Borders
        dpg.add_theme_color(dpg.mvThemeCol_Border, c["border"])
        dpg.add_theme_color(dpg.mvThemeCol_BorderShadow, (0, 0, 0, 0))

        # Text
        dpg.add_theme_color(dpg.mvThemeCol_Text, c["text"])
        dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, c["text_dim"])

        # Buttons
        dpg.add_theme_color(dpg.mvThemeCol_Button, c["button"])
        dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, c["button_hover"])
        dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, c["button_active"])

        # Headers (collapsing, table)
        dpg.add_theme_color(dpg.mvThemeCol_Header, c["header"])
        dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, c["header_hover"])
        dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, c["header_hover"])

        # Frames (inputs, checkboxes)
        dpg.add_theme_color(dpg.mvThemeCol_FrameBg, c["bg_elevated"])
        dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, c["button_hover"])
        dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, c["button_active"])

        # Scrollbar
        dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, c["scrollbar"])
        dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, c["scrollbar_grab"])
        dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, c["scrollbar_grab"])
        dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, c["scrollbar_grab"])

        # Title bar
        dpg.add_theme_color(dpg.mvThemeCol_TitleBg, c["bg_surface"])
        dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive, c["bg_surface"])

        # Tabs
        dpg.add_theme_color(dpg.mvThemeCol_Tab, c["bg_elevated"])
        dpg.add_theme_color(dpg.mvThemeCol_TabHovered, c["button_hover"])
        dpg.add_theme_color(dpg.mvThemeCol_TabActive, c["accent"])

        # Spacing and rounding
        dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)
        dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 8)
        dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 6)
        dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 6)
        dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 12, 12)


def _build_button_theme(tag: str, bg: tuple, hover: tuple, active: tuple, text: tuple = (255, 255, 255)) -> None:
    """Create a button-specific theme."""
    with dpg.theme(tag=tag), dpg.theme_component(dpg.mvButton):
        dpg.add_theme_color(dpg.mvThemeCol_Button, bg)
        dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, hover)
        dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, active)
        dpg.add_theme_color(dpg.mvThemeCol_Text, text)


def _build_sidebar_themes() -> None:
    """Create sidebar navigation button themes."""
    # Normal (transparent)
    with dpg.theme(tag="sidebar_button"), dpg.theme_component(dpg.mvButton):
        dpg.add_theme_color(dpg.mvThemeCol_Button, (0, 0, 0, 0))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (0, 0, 0, 0))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (255, 255, 255, 20))

    # Active (accent highlight)
    with dpg.theme(tag="sidebar_button_active"), dpg.theme_component(dpg.mvButton):
        dpg.add_theme_color(dpg.mvThemeCol_Button, (88, 166, 255, 40))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (88, 166, 255, 40))
        dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (88, 166, 255, 50))


def _build_badge_themes() -> None:
    """Create status badge themes."""
    badges = [
        ("badge_pending", (250, 180, 50)),
        ("badge_processing", (88, 166, 255)),
        ("badge_done", (80, 200, 120)),
        ("badge_failed", (240, 80, 80)),
    ]
    for name, color in badges:
        with dpg.theme(tag=name), dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, color)
            dpg.add_theme_color(dpg.mvThemeCol_Text, (255, 255, 255))
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 10)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 3)


# ── Public API ──────────────────────────────────────────────


def setup_themes() -> None:
    """Create all application themes.

    Must be called once before creating any UI elements.
    """
    # Base themes
    _build_base_theme("dark_theme", _dark_palette())
    _build_base_theme("light_theme", _light_palette())

    # Action button themes
    _build_button_theme(
        "accent_button",
        bg=(88, 166, 255),
        hover=(110, 180, 255),
        active=(70, 150, 240),
    )
    _build_button_theme(
        "success_button",
        bg=(50, 140, 80),
        hover=(60, 160, 95),
        active=(45, 130, 75),
    )
    _build_button_theme(
        "danger_button",
        bg=(180, 50, 50),
        hover=(200, 60, 60),
        active=(160, 45, 45),
    )

    # Sidebar themes
    _build_sidebar_themes()

    # Badge themes
    _build_badge_themes()
