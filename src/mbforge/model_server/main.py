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

from ..utils.exceptions import MBForgeError
from .routers import embed
from .routers import environment
from .routers import health
from .routers import llm
from .routers import moldet
from .routers import tools
from .routers import vlm

logger = logging.getLogger("mbforge.startup")


def _prewarm_models():
    """在后台线程中预加载核心模型，避免首次请求阻塞."""
    try:
        from .models.llm import get_llm

        get_llm()
        logger.info("LLM model prewarmed")
    except Exception as e:
        logger.warning(f"LLM prewarm failed: {e}")

    try:
        from .models.embedder import get_embedder

        get_embedder()
        logger.info("Embedder model prewarmed")
    except Exception as e:
        logger.warning(f"Embedder prewarm failed: {e}")

    try:
        from .models.reranker import get_reranker

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
    """应用生命周期：启动时检查环境 + 后台预热模型."""
    # 1. 同步环境检查（快速，不下载）
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _check_environment)

    # 2. 后台预热模型
    loop.run_in_executor(None, _prewarm_models)
    yield


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


# 注册路由
app.include_router(llm.router, prefix="/api/v1/llm", tags=["llm"])
app.include_router(embed.router, prefix="/api/v1", tags=["embed"])
app.include_router(vlm.router, prefix="/api/v1/vlm", tags=["vlm"])
app.include_router(moldet.router, prefix="/api/v1/moldet", tags=["moldet"])
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(tools.router, prefix="/api/v1/tools", tags=["tools"])
app.include_router(
    environment.router, prefix="/api/v1/environment", tags=["environment"]
)
