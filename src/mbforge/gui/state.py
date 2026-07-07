"""Global application state for MBForge Dear PyGui frontend."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AppState:
    """Global application state."""

    # Server
    port: int = 18792
    base_url: str = ""

    # Library
    library_root: str = ""
    library_name: str = ""
    doc_count: int = 0
    mol_count: int = 0
    recent_libraries: list[dict] = field(default_factory=list)

    # Navigation
    active_view: str = "welcome"

    # Settings
    theme: str = "dark"
    language: str = "zh-CN"

    def __post_init__(self):
        if not self.base_url:
            self.base_url = f"http://127.0.0.1:{self.port}"
