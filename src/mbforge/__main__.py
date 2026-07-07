"""python -m mbforge — start the MBForge web application."""

import os
import sys

if __name__ == "__main__":
    from .utils.paths import DEFAULT_SIDECAR_PORT

    port = DEFAULT_SIDECAR_PORT
    host = os.environ.get("MBFORGE_HOST", "127.0.0.1")
    gui_mode = False
    dev_mode = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--gui":
            gui_mode = True
        elif args[i] == "--dev":
            dev_mode = True
        elif args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
            i += 1
        elif args[i] == "--host" and i + 1 < len(args):
            host = args[i + 1]
            i += 1
        elif args[i] == "--no-browser":
            os.environ["MBFORGE_NO_BROWSER"] = "1"
        i += 1

    if gui_mode:
        from .gui import launch
        launch(port=port, dev=dev_mode)
    else:
        # Frozen / Docker 模式：自动开浏览器（除非禁用）
        _auto_browser = (
            (getattr(sys, "frozen", False) or os.environ.get("MBFORGE_IN_DOCKER") == "1")
            and os.environ.get("MBFORGE_NO_BROWSER") != "1"
            and host in ("127.0.0.1", "localhost", "0.0.0.0")
        )
        if _auto_browser:
            import threading
            import time
            import webbrowser

            def _open():
                time.sleep(2)
                url = f"http://127.0.0.1:{port}"
                try:
                    webbrowser.open(url)
                    print(f"\n>>> MBForge running at {url}\n")
                except Exception:
                    pass

            threading.Thread(target=_open, daemon=True).start()

        import uvicorn
        uvicorn.run(
            "mbforge.app:app",
            host=host,
            port=port,
            reload=False,
            log_level="warning",
        )
