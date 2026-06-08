"""python -m mbforge 入口 — 启动 FastAPI sidecar."""

import sys

if __name__ == "__main__":
    import uvicorn
    from .model_server.main import app
    from .utils.constants import DEFAULT_SIDECAR_PORT

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SIDECAR_PORT,
    )
