"""MBForge 启动脚本 — 同时启动后端和前端开发服务器."""

import subprocess
import sys
import signal
import os
from pathlib import Path

ROOT = Path(__file__).parent


def main():
    procs = []

    # 1. 启动后端 (FastAPI)
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "mbforge.app:app",
         "--host", "127.0.0.1", "--port", "18792", "--no-access-log"],
        cwd=str(ROOT),
    )
    procs.append(backend)

    # 2. 启动前端 (Vite)
    frontend_dir = ROOT / "frontend"
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    frontend = subprocess.Popen(
        [npm, "run", "dev"],
        cwd=str(frontend_dir),
    )
    procs.append(frontend)

    # 优雅退出
    def shutdown(*_):
        for p in procs:
            p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("\n" + "=" * 50)
    print("  MBForge 启动中...")
    print("  后端: http://127.0.0.1:18792")
    print("  前端: http://localhost:5173")
    print("  按 Ctrl+C 停止所有服务")
    print("=" * 50 + "\n")

    # 等待前端就绪后自动打开浏览器
    import webbrowser
    import time

    def open_browser():
        time.sleep(3)  # 等待 Vite 启动
        webbrowser.open("http://localhost:5173")

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    # 等待任一进程退出
    try:
        while True:
            for p in procs:
                if p.poll() is not None:
                    shutdown()
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
