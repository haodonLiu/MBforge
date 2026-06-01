"""FastAPI 模型服务入口."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

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
from .routers import (
    llm, embed, rerank, vlm, moldet, uniparser,
    health, project, kb, molecule, file,
    settings, download, chem, environment, resources,
)

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


# 注册路由
app.include_router(llm.router, prefix="/api/v1/llm", tags=["llm"])
app.include_router(embed.router, prefix="/api/v1", tags=["embed"])
app.include_router(rerank.router, prefix="/api/v1", tags=["rerank"])
app.include_router(vlm.router, prefix="/api/v1/vlm", tags=["vlm"])
app.include_router(moldet.router, prefix="/api/v1/moldet", tags=["moldet"])
app.include_router(uniparser.router, prefix="/api/v1/uniparser", tags=["uniparser"])
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(project.router, prefix="/api/v1/project", tags=["project"])
app.include_router(kb.router, prefix="/api/v1/kb", tags=["kb"])
app.include_router(molecule.router, prefix="/api/v1/molecule", tags=["molecule"])
app.include_router(file.router, prefix="/api/v1/file", tags=["file"])
app.include_router(settings.router, prefix="/api/v1/settings", tags=["settings"])
app.include_router(download.router, prefix="/api/v1/download", tags=["download"])
app.include_router(chem.router, prefix="/api/v1/chem", tags=["chem"])
app.include_router(environment.router, prefix="/api/v1/environment", tags=["environment"])
app.include_router(resources.router, prefix="/api/v1/resources", tags=["resources"])
