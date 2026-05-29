"""FastAPI 模型服务入口."""

from __future__ import annotations

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
from .routers import llm, embed, rerank, vlm, health, uniparser, moldet, project, kb, molecule, agent, file, settings, download

app = FastAPI(title="MBForge Model Server", version="1.1.0")

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
app.include_router(uniparser.router, prefix="/api/v1/uniparser", tags=["uniparser"])
app.include_router(moldet.router, prefix="/api/v1/moldet", tags=["moldet"])
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(project.router, prefix="/api/v1/project", tags=["project"])
app.include_router(kb.router, prefix="/api/v1/kb", tags=["kb"])
app.include_router(molecule.router, prefix="/api/v1/molecule", tags=["molecule"])
app.include_router(agent.router, prefix="/api/v1/agent", tags=["agent"])
app.include_router(file.router, prefix="/api/v1/file", tags=["file"])
app.include_router(settings.router, prefix="/api/v1/settings", tags=["settings"])
app.include_router(download.router, prefix="/api/v1/download", tags=["download"])
