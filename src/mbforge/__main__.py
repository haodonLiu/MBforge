"""python -m mbforge — start the MBForge web application."""

import sys

if __name__ == "__main__":
    from .utils.paths import DEFAULT_SIDECAR_PORT

    port = DEFAULT_SIDECAR_PORT
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
        i += 1

    if gui_mode:
        from .gui import launch
        launch(port=port, dev=dev_mode)
    else:
        import uvicorn
        uvicorn.run(
            "mbforge.app:app",
            host="127.0.0.1",
            port=port,
            reload=False,
        )
