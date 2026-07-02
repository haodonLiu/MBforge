"""Shared color constants for MBForge GUI."""

from __future__ import annotations

# ── Status Colors ───────────────────────────────────────────

STATUS_COLORS = {
    "pending": (250, 180, 50),
    "processing": (88, 166, 255),
    "done": (80, 200, 120),
    "failed": (240, 80, 80),
    "active": (80, 200, 120),
    "inactive": (140, 140, 150),
}

# ── Semantic Colors ─────────────────────────────────────────

COLOR_TEXT = (200, 200, 210)
COLOR_TEXT_DIM = (140, 140, 150)
COLOR_TEXT_MUTED = (100, 100, 110)
COLOR_ACCENT = (88, 166, 255)
COLOR_SUCCESS = (80, 200, 120)
COLOR_WARNING = (250, 180, 50)
COLOR_ERROR = (240, 80, 80)

# ── Semantic Aliases ────────────────────────────────────────

COLOR_USER = COLOR_ACCENT
COLOR_ASSISTANT = COLOR_TEXT
COLOR_SYSTEM = COLOR_TEXT_DIM

# ── Helpers ─────────────────────────────────────────────────


def get_status_color(status: str) -> tuple:
    """Get color for a status string."""
    return STATUS_COLORS.get(status, COLOR_TEXT_DIM)
