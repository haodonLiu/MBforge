"""MBForge Web Application — FastAPI factory.

Pure-Python backend serving both the API and the React frontend.
Replaces the Tauri/Rust shell with a standard web application.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .utils.logger import get_logger

logger = get_logger("mbforge.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    logger.info("MBForge web application starting...")
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _check_environment)
    try:
        yield
    finally:
        logger.info("MBForge shutting down...")
        _shutdown_backends()
        pending = [
            t
            for t in asyncio.all_tasks()
            if t is not asyncio.current_task() and not t.done()
        ]
        if pending:
            for t in pending:
                t.cancel()
            await asyncio.wait(pending, timeout=1.0)
        logger.info("Shutdown complete")


def _check_environment() -> None:
    try:
        from .core.resource_manager import ResourceManager

        report = ResourceManager.check_all()
        logger.info("Environment: %s", report.summary)
    except Exception as e:
        logger.warning("Environment check failed: %s", e)


def _shutdown_backends() -> None:
    from .backends import moldet, molscribe

    for mod in [molscribe, moldet]:
        try:
            mod.unload()
        except Exception:
            pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="MBForge",
        description="Molecular Knowledge Base & AI Workbench",
        version="0.4.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register all routers
    from .routers import (
        agent,
        chem,
        coref,
        detection_cache,
        documents,
        events,
        health,
        knowledge_base,
        molecule,
        notes,
        ocr,
        pdf,
        pipeline,
        project,
        resource,
        sar,
        settings,
        text,
    )

    app.include_router(project.router, prefix="/api/v1/project", tags=["project"])
    app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
    app.include_router(pipeline.router, prefix="/api/v1/pipeline", tags=["pipeline"])
    app.include_router(knowledge_base.router, prefix="/api/v1/kb", tags=["kb"])
    app.include_router(molecule.router, prefix="/api/v1/molecule", tags=["molecule"])
    app.include_router(agent.router, prefix="/api/v1/agent", tags=["agent"])
    app.include_router(chem.router, prefix="/api/v1/chem", tags=["chem"])
    app.include_router(detection_cache.router, prefix="/api/v1/detection-cache", tags=["detection"])
    app.include_router(notes.router, prefix="/api/v1/notes", tags=["notes"])
    app.include_router(settings.router, prefix="/api/v1/settings", tags=["settings"])
    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(resource.router, prefix="/api/v1", tags=["resource"])
    app.include_router(events.router, prefix="/api/v1/events", tags=["events"])
    app.include_router(pdf.router, prefix="/api/v1/pdf", tags=["pdf"])
    app.include_router(coref.router, prefix="/api/v1/coref", tags=["coref"])
    app.include_router(sar.router, prefix="/api/v1/sar", tags=["sar"])
    app.include_router(text.router, prefix="/api/v1", tags=["text"])
    app.include_router(ocr.router, prefix="/api/v1/ocr", tags=["ocr"])

    # Mount existing model server endpoints under /api/v1/models/*
    from .server import app as model_server

    app.mount("/api/v1/models", model_server)

    # Serve React frontend in production
    frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
        logger.info("Frontend: %s", frontend_dist)

    return app


app = create_app()
