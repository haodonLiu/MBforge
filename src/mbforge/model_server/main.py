"""FastAPI 模型服务入口."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import llm, embed, rerank, vlm, health, uniparser, moldet, project, kb, molecule, agent, file

app = FastAPI(title="MBForge Model Server", version="1.1.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
