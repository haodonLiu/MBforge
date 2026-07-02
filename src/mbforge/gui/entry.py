"""Entry point for MBForge Dear PyGui native frontend."""

from __future__ import annotations

import atexit
import signal
import sys
import threading
import time
import urllib.error
import urllib.request

from ..utils.logger import get_logger

logger = get_logger(__name__)

BACKEND_PORT = 18792
_backend_process = None


def _load_cjk_font(dpg) -> None:
    """Load a CJK font for Chinese character support.

    Tries Microsoft YaHei (Windows), then Noto Sans CJK (cross-platform).
    Falls back to default font if none found.
    """
    import os
    from pathlib import Path

    # Font candidates (Windows paths)
    cjk_fonts = [
        # Windows common fonts
        "C:/Windows/Fonts/msyh.ttc",       # Microsoft YaHei
        "C:/Windows/Fonts/msyhbd.ttc",      # Microsoft YaHei Bold
        "C:/Windows/Fonts/simsun.ttc",      # SimSun
        "C:/Windows/Fonts/simhei.ttf",      # SimHei
        "C:/Windows/Fonts/msyhsl.ttc",      # Microsoft YaHei Light
        # Noto fonts (if installed)
        str(Path.home() / ".fonts/NotoSansCJK-Regular.ttc"),
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    ]

    for font_path in cjk_fonts:
        if os.path.exists(font_path):
            try:
                with dpg.font(font_path, 16) as default_font:
                    # Add CJK character ranges
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Full)
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Simplified_Common)
                dpg.bind_font(default_font)
                logger.info("Loaded CJK font: %s", font_path)
                return
            except Exception as e:
                logger.warning("Failed to load font %s: %s", font_path, e)

    logger.warning("No CJK font found, Chinese characters may not display correctly")


def _start_backend(port: int = BACKEND_PORT) -> None:
    """Start FastAPI backend in a background thread."""
    import uvicorn

    logger.info("Starting backend on port %d", port)
    try:
        uvicorn.run(
            "mbforge.app:app",
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    except OSError as e:
        if "address already in use" in str(e).lower() or "10048" in str(e):
            logger.info("Port %d already in use, assuming backend is running", port)
        else:
            raise


def _wait_for_backend(port: int, timeout: float = 30.0) -> bool:
    """Wait until the backend is ready."""
    url = f"http://127.0.0.1:{port}/api/v1/health"
    logger.info("Waiting for backend at %s ...", url)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            logger.info("Backend ready")
            return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.3)
    logger.error("Backend failed to start within %ds", timeout)
    return False


def launch(port: int = BACKEND_PORT, dev: bool = False) -> None:
    """Launch MBForge as a native Dear PyGui desktop application.

    Args:
        port: Backend port number.
        dev: If True, enable debug mode.
    """
    try:
        import dearpygui.dearpygui as dpg
    except ImportError:
        logger.error(
            "dearpygui is not installed. Run: pip install dearpygui"
        )
        sys.exit(1)

    # Check if backend is already running
    backend_already_running = False
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=2)
        backend_already_running = True
        logger.info("Backend already running on port %d", port)
    except Exception:
        pass

    # Start backend if not already running
    backend_thread = None
    if not backend_already_running:
        backend_thread = threading.Thread(
            target=_start_backend,
            args=(port,),
            daemon=True,
        )
        backend_thread.start()

    # Wait for backend
    if not _wait_for_backend(port):
        logger.error("Backend failed to start")
        sys.exit(1)

    # Initialize Dear PyGui
    dpg.create_context()

    # Load CJK font for Chinese character support
    _load_cjk_font(dpg)

    dpg.create_viewport(
        title="MBForge - Molecular Knowledge Base",
        width=1400,
        height=900,
    )

    # Create and run application
    from .app import MBForgeApp

    app = MBForgeApp(port=port, dev=dev)
    app.create()

    dpg.setup_dearpygui()
    dpg.show_viewport()

    # Register cleanup
    def _cleanup():
        app.shutdown()

    atexit.register(_cleanup)

    def _signal_handler(sig, frame):
        logger.info("Received signal %s, shutting down...", sig)
        app.shutdown()
        dpg.destroy_context()
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        dpg.start_dearpygui()
    finally:
        app.shutdown()
        dpg.destroy_context()
