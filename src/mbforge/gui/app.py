"""Main application class for MBForge Dear PyGui frontend."""

from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path
from threading import Thread

import dearpygui.dearpygui as dpg

from .api.client import ApiClient
from .components.sidebar import Sidebar
from .components.header import Header
from .components.toasts import ToastManager, set_toast_manager
from .state import AppState
from .utils.constants import (
    WINDOW_TITLE,
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
)
from .utils.themes import setup_themes
from .utils.i18n import t
from .utils.threading import safe_set_value, clear_container
from .views.welcome import WelcomeView
from .views.workspace import WorkspaceView
from .views.discover import DiscoverView
from .views.molecules import MoleculesView
from .views.queue import QueueView
from .views.notes import NotesView
from .views.settings import SettingsView

from ..utils.logger import get_logger

logger = get_logger(__name__)


class MBForgeApp:
    """Main application managing the window and views.

    Lifecycle: __init__ → create → (run via dpg) → shutdown
    """

    def __init__(self, port: int = 18792, dev: bool = False):
        self.state = AppState(port=port)
        self.api = ApiClient(self.state.base_url)
        self.views: dict[str, object] = {}
        self.sidebar: Sidebar | None = None
        self.header: Header | None = None
        self.toast = ToastManager()
        self._shutdown = False

    def create(self) -> None:
        """Create the main window and all UI components."""
        setup_themes()
        self.toast.create()
        set_toast_manager(self.toast)

        # Create main window with context manager
        with dpg.window(
            tag="main_window",
            label=WINDOW_TITLE,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            no_title_bar=True,
            no_move=True,
            no_resize=True,
        ):
            # Main horizontal layout
            with dpg.group(horizontal=True):
                # Sidebar
                self.sidebar = Sidebar(on_navigate=self._on_navigate)
                self.sidebar.create("main_window")

                # Content area
                with dpg.group():
                    self.header = Header()
                    self.header.create("main_window")
                    dpg.add_separator()
                    dpg.add_child_window(
                        tag="content_area",
                        autosize_x=True,
                        autosize_y=True,
                        border=False,
                    )

        self._create_views()
        self._load_recent_libraries()
        self._show_view("welcome")

        # Register shutdown handler
        dpg.set_frame_callback(1, callback=self._on_first_frame)

    def _on_first_frame(self) -> None:
        """Called after first frame renders."""
        pass

    def shutdown(self) -> None:
        """Clean up resources."""
        if self._shutdown:
            return
        self._shutdown = True
        logger.info("Shutting down MBForge GUI...")

        # Stop polling in queue view
        if "queue" in self.views:
            view = self.views["queue"]
            if hasattr(view, "stop_polling"):
                view.stop_polling()

        # Stop SSE streams
        if "discover" in self.views:
            view = self.views["discover"]
            if hasattr(view, "sse"):
                view.sse.stop()

        # Close API client
        self.api.close()

        logger.info("Shutdown complete")

    def _create_views(self) -> None:
        """Create all view instances."""
        view_classes = {
            "welcome": WelcomeView,
            "workspace": WorkspaceView,
            "discover": DiscoverView,
            "molecules": MoleculesView,
            "queue": QueueView,
            "notes": NotesView,
            "settings": SettingsView,
        }

        for name, cls in view_classes.items():
            view = cls(self)
            view.create("content_area")
            self.views[name] = view

    def _on_navigate(self, view_name: str) -> None:
        """Handle navigation."""
        self._show_view(view_name)

    def _show_view(self, view_name: str) -> None:
        """Show a view and hide others."""
        for name, view in self.views.items():
            if name != view_name:
                view.hide()

        if view_name in self.views:
            view = self.views[view_name]
            view.show()
            view.refresh()
            self.state.active_view = view_name

        if self.sidebar:
            self.sidebar.set_active(view_name)

    def open_project(self, root: str) -> None:
        """Open a project in a background thread."""
        Thread(target=self._open_project_worker, args=(root,), daemon=True).start()

    def _open_project_worker(self, root: str) -> None:
        """Background worker for opening a project."""
        try:
            resp = self.api.open_project(root)
            if resp.success:
                self.state.library_root = resp.root
                self.state.library_name = resp.name or Path(root).name
                self.state.doc_count = resp.doc_count

                if self.header:
                    self.header.set_project(self.state.library_name)

                self._save_to_recent(root, self.state.library_name)
                self._show_view("workspace")
                self.toast.show(f"Opened: {self.state.library_name}", "success")
            else:
                self.toast.show("Failed to open project", "error")
        except Exception as e:
            logger.error("Failed to open project: %s", e)
            self.toast.show(f"Error: {e}", "error")

    def _load_recent_libraries(self) -> None:
        """Load recent libraries from config.

        On disk the legacy key ``recent_projects`` is preserved so existing
        ``gui_state.json`` files load without migration. The in-memory field
        is renamed to ``recent_libraries`` to match the rest of the code.
        """
        config_path = self._config_path()
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                self.state.recent_libraries = data.get("recent_projects", [])
            except Exception as e:
                logger.warning("Failed to load recent libraries: %s", e)
                self.state.recent_libraries = []

    def _save_to_recent(self, root: str, name: str) -> None:
        """Save library to recent list."""
        recent = [p for p in self.state.recent_libraries if p.get("root") != root]
        recent.insert(0, {"root": root, "name": name})
        recent = recent[:10]
        self.state.recent_libraries = recent

        config_path = self._config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Persist under the legacy key for backward-compat with
            # existing gui_state.json on disk.
            config_path.write_text(
                json.dumps({"recent_projects": recent}, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Failed to save recent libraries: %s", e)

    def _config_path(self) -> Path:
        """Get config file path."""
        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        else:
            base = Path.home() / ".config"
        return base / "MBForge" / "gui_state.json"
