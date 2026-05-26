"""Zotero Bridge HTTP 服务器.

基于 aiohttp 提供本地 API，默认监听 localhost:8233。
"""

from __future__ import annotations

from pathlib import Path

from aiohttp import web

from ..utils.logger import get_logger
from .handlers import health, import_items

logger = get_logger(__name__)


def create_app(project_root: Path) -> web.Application:
    """创建并配置 aiohttp Application."""
    app = web.Application()
    app["project_root"] = Path(project_root).resolve()

    # CORS：允许 Zotero 插件跨域访问（Zotero fetch 默认同源，但插件环境特殊）
    async def cors_middleware(request: web.Request, handler):
        if request.method == "OPTIONS":
            return web.Response(
                status=200,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type",
                },
            )
        response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    app.middlewares.append(cors_middleware)

    # 路由
    app.router.add_get("/api/v1/zotero/health", health)
    app.router.add_post("/api/v1/zotero/import", import_items)

    return app


def run_server(project_root: Path, host: str = "127.0.0.1", port: int = 8233) -> None:
    """启动 Zotero Bridge 服务（阻塞调用）."""
    app = create_app(project_root)
    logger.info("Zotero Bridge 启动于 http://%s:%d (项目: %s)", host, port, project_root)
    web.run_app(app, host=host, port=port, print=None)
