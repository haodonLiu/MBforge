"""python -m mbforge — start the MBForge web application."""

import sys

if __name__ == "__main__":
    import uvicorn

    from .utils.constants import DEFAULT_SIDECAR_PORT

    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SIDECAR_PORT
    uvicorn.run(
        "mbforge.app:app",
        host="127.0.0.1",
        port=port,
        reload=False,
    )
