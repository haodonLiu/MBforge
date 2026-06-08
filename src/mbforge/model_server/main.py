"""FastAPI 模型服务入口."""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

# Windows console 默认 codepage（cp1252 / GBK）编码不了 ✓/✗ 这类 Unicode，
# Python logging 一旦 encode 失败会在 StreamHandler 抛 UnicodeEncodeError，
# 进而让 lifespan 里的 _check_environment 线程整个崩。
# 强制把 stdout/stderr 切到 UTF-8，errors="backslashreplace" 兜底防止异常字符。
#
# 两道防线：
#   1) 先尝试 reconfigure —— 对 console 输出最干净；
#   2) reconfigure 失败时（旧 Python / 管道不支持），用 TextIOWrapper
#      重包 sys.stdout.buffer / sys.stderr.buffer，强制 UTF-8 编码。
if sys.platform == "win32":
    import io as _io

    for _stream_name in ("stdout", "stderr"):
        _stream = getattr(sys, _stream_name)
        try:
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, OSError, ValueError):
            # reconfigure 失败（管道不支持 / 旧版本） —— 用 TextIOWrapper 重包 buffer
            try:
                _buffer = _stream.buffer
                _new_stream = _io.TextIOWrapper(
                    _buffer,
                    encoding="utf-8",
                    errors="backslashreplace",
                    line_buffering=True,
                )
                setattr(sys, _stream_name, _new_stream)
            except (AttributeError, OSError):
                # 既不能 reconfigure 也没有 buffer —— 最后只能放弃，让 StreamHandler
                # 自行兜底（这种情况下 Python 极老，可能性很小）
                pass

# Load .env before anything else
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..utils.helpers import MBForgeError
from .routers import (
    embed_router,
    environment_router,
    health_router,
    moldet_router,
    vlm_router,
)

logger = logging.getLogger("mbforge.startup")


def _prewarm_models():
    """在后台线程中预加载核心模型，避免首次请求阻塞.

    注意：LLM **不**在这里预热 — LLM 由 Rust core 直接调用
    `MBFORGE_LLM_*` 端点（参见 `core/agent/rig_adapter`），不再经过此 sidecar。
    """
    try:
        from mbforge.models.embedding import get_embedder

        get_embedder()
        logger.info("Embedder model prewarmed")
    except Exception as e:
        logger.warning(f"Embedder prewarm failed: {e}")

    try:
        from mbforge.models.rerank import get_reranker

        get_reranker()
        logger.info("Reranker model prewarmed")
    except Exception as e:
        logger.warning(f"Reranker prewarm failed: {e}")


def _check_environment():
    """启动时环境检查 — 记录资源状态到日志."""
    try:
        from ..core.resource_manager import ResourceManager

        report = ResourceManager.check_all()
        logger.info(f"Environment check: {report.summary}")
        for r in report.resources:
            if r.status.value == "ready":
                logger.info(f"  ✓ {r.name}: ready {r.local_path}")
            else:
                logger.info(f"  ✗ {r.name}: {r.status.value}")
    except Exception as e:
        logger.warning(f"Environment check failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时检查环境 + 后台预热模型，关闭时清理."""
    import time as _time

    started_at = _time.time()
    logger.info("Sidecar starting up...")

    # 1. 同步环境检查（快速，不下载）
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _check_environment)

    # 2. 后台预热模型
    loop.run_in_executor(None, _prewarm_models)

    try:
        yield
    finally:
        # Phase 3 优雅退出：记录运行时长 + 取消后台 executor
        # 任务 + 关闭连接池。Tauri SIGTERM 后此 lifespan 进入 finally 分支。
        uptime = _time.time() - started_at
        logger.info(f"Sidecar shutting down (uptime {uptime:.1f}s)...")

        # 关闭 httpx / aiohttp 客户端
        try:
            from mbforge.utils.singleton import close_all_singletons

            await close_all_singletons()
        except Exception as e:
            logger.warning(f"close_all_singletons failed: {e}")

        # 取消未完成的 executor 任务
        try:
            pending = [
                t for t in asyncio.all_tasks()
                if t is not asyncio.current_task() and not t.done()
            ]
            if pending:
                logger.info(f"Cancelling {len(pending)} pending tasks...")
                for t in pending:
                    t.cancel()
                # 给任务 1 秒时间响应 cancel
                await asyncio.wait(pending, timeout=1.0)
        except Exception as e:
            logger.warning(f"Task cancellation failed: {e}")

        logger.info("Sidecar shutdown complete")


app = FastAPI(title="MBForge Model Server", version="1.1.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler for structured error responses
@app.exception_handler(MBForgeError)
async def mbforge_error_handler(request: Request, exc: MBForgeError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.message,
            "error_code": exc.error_code,
        },
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled error on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": str(exc),
            "error_code": "internal_error",
        },
    )


# 注册路由（注意：LLM 路由已移除 — LLM 由 Rust core 直连 MBFORGE_LLM_* 端点）
app.include_router(embed_router, prefix="/api/v1", tags=["embed"])
app.include_router(vlm_router, prefix="/api/v1/vlm", tags=["vlm"])
app.include_router(moldet_router, prefix="/api/v1/moldet", tags=["moldet"])
app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(environment_router, prefix="/api/v1/environment", tags=["environment"])
