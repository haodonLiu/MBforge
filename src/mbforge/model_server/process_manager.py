"""模型服务子进程管理."""

from __future__ import annotations

import subprocess
import sys
import time
from typing import Optional

import httpx


class ModelServerManager:
    """管理 FastAPI 模型服务子进程."""

    def __init__(self, host: str = "127.0.0.1", port: int = 18792, startup_timeout: int = 120):
        self.host = host
        self.port = port
        self.startup_timeout = startup_timeout
        self._process: Optional[subprocess.Popen] = None
        self._base_url = f"http://{host}:{port}"

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        """启动 FastAPI 子进程并等待就绪."""
        if self.is_running:
            return

        self._process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "mbforge.model_server.main:app",
                "--host",
                self.host,
                "--port",
                str(self.port),
                "--workers",
                "1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 等待服务就绪
        self._wait_ready()

    def _wait_ready(self) -> None:
        """轮询 /health 直到服务就绪或超时."""
        deadline = time.time() + self.startup_timeout
        while time.time() < deadline:
            if self._process is not None and self._process.poll() is not None:
                return
            try:
                resp = httpx.get(f"{self._base_url}/api/v1/health", timeout=2.0)
                if resp.status_code == 200:
                    return
            except Exception:
                pass
            time.sleep(1.0)

    def stop(self) -> None:
        """停止 FastAPI 子进程."""
        if self._process is None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        self._process = None

    async def get_health_async(self) -> dict:
        """异步查询健康状态."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/v1/health")
                return resp.json()
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_health(self) -> dict:
        """同步查询健康状态."""
        try:
            resp = httpx.get(f"{self._base_url}/api/v1/health", timeout=5.0)
            return resp.json()
        except Exception as e:
            return {"status": "error", "error": str(e)}
