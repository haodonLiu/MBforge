"""MBForge Web Application — FastAPI factory.

Pure-Python backend serving both the API and the React frontend.
Replaces the Tauri/Rust shell with a standard web application.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .utils.helpers import MBForgeError
from .utils.logger import (
    get_logger,
    push_diagnostic,
    reset_request_path,
    set_request_path,
)
from .utils.paths import APP_VERSION

logger = get_logger("mbforge.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    logger.info("MBForge web application starting...")
    from .server import _prewarm
    from .utils.helpers import check_environment, shutdown_backends

    # Await prewarm before yielding so the app is actually ready to serve
    # requests that touch local models. Failures inside the helpers are
    # already logged as non-fatal warnings.
    loop = asyncio.get_running_loop()
    env_future = loop.run_in_executor(None, check_environment)
    prewarm_future = loop.run_in_executor(None, _prewarm)
    await asyncio.gather(env_future, prewarm_future)
    try:
        yield
    finally:
        logger.info("MBForge shutting down...")
        shutdown_backends()
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


# ---------------------------------------------------------------------------
# Request-path middleware + central exception handlers
# ---------------------------------------------------------------------------
#
# Why these live in `app.py` rather than `server.py`:
#   `server.py:117,127` registers handlers on the *mounted sub-app*
#   (Starlette `Mount("/api/v1/models", model_server)`) — that sub-app is
#   a separate routing graph with its own exception handlers. The handlers
#   below cover every `include_router(...)` route on the main app, which
#   is where 17 of the 18 production routers live.


async def _request_path_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Push the current request path into a ContextVar so JSON file logs
    and the diagnostic ring buffer can attach it without API changes."""
    token = set_request_path(request.url.path)
    try:
        return await call_next(request)
    finally:
        reset_request_path(token)


def _severity_to_level(severity: str) -> int:
    return {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "fatal": logging.CRITICAL,
    }.get(severity, logging.ERROR)


async def _mbforge_error_handler(request: Request, exc: MBForgeError) -> JSONResponse:
    """Central handler for MBForgeError + subclasses.

    Logs at the level implied by `exc.severity`, pushes a record into the
    diagnostic ring buffer, and returns a JSON body the front-end can
    introspect via `AppError`.
    """
    level = _severity_to_level(exc.severity)
    logger.log(
        level,
        "MBForgeError on %s: %s [%s/%s]",
        request.url.path,
        exc.message,
        exc.error_code,
        exc.category,
        extra={
            "mbforge_error_code": exc.error_code,
            "mbforge_status_code": exc.status_code,
            "mbforge_severity": exc.severity,
            "mbforge_category": exc.category,
            "mbforge_context": exc.context,
        },
        exc_info=isinstance(exc, Exception),
    )
    push_diagnostic(
        {
            "level": logging.getLevelName(level),
            "logger": "mbforge.app.exception_handler",
            "message": exc.message,
            "error_code": exc.error_code,
            "status_code": exc.status_code,
            "severity": exc.severity,
            "category": exc.category,
            "context": exc.context,
        }
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.message,
            "detail": exc.detail,
            "error_code": exc.error_code,
            "severity": exc.severity,
            "category": exc.category,
            "context": exc.context,
            "timestamp": time.time(),
        },
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for non-MBForgeError exceptions. Always fatal, generic code."""
    logger.error(
        "Unhandled on %s: %s",
        request.url.path,
        exc,
        exc_info=True,
        extra={
            "mbforge_error_code": "internal_error",
            "mbforge_status_code": 500,
            "mbforge_severity": "fatal",
            "mbforge_category": "unhandled",
            "mbforge_context": {"exception_type": type(exc).__name__},
        },
    )
    push_diagnostic(
        {
            "level": "CRITICAL",
            "logger": "mbforge.app.exception_handler",
            "message": str(exc) or type(exc).__name__,
            "error_code": "internal_error",
            "status_code": 500,
            "severity": "fatal",
            "category": "unhandled",
            "context": {"exception_type": type(exc).__name__},
        }
    )
    # Operator-friendly default; do not leak stack frames to the client.
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "error_code": "internal_error",
            "severity": "fatal",
            "category": "unhandled",
            "context": {},
            "timestamp": time.time(),
        },
    )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="MBForge",
        description="Molecular Knowledge Base & AI Workbench",
        version=APP_VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers run before route resolution returns, capturing
    # errors thrown anywhere in the main app graph.
    app.add_exception_handler(MBForgeError, _mbforge_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)

    # Request-path ContextVar middleware (must be added before any
    # router-level middleware to ensure it covers all routes).
    app.middleware("http")(_request_path_middleware)

    # Register all routers
    from .routers import (
        agent,
        chem,
        coref,
        detection_cache,
        diagnostics,
        documents,
        events,
        health,
        knowledge_base,
        library,
        molecule,
        notes,
        ocr,
        pdf,
        pipeline,
        resource,
        sar,
        settings,
        text,
    )

    app.include_router(library.router, prefix="/api/v1/library", tags=["library"])
    app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
    app.include_router(pipeline.router, prefix="/api/v1/pipeline", tags=["pipeline"])
    app.include_router(knowledge_base.router, prefix="/api/v1/kb", tags=["kb"])
    app.include_router(molecule.router, prefix="/api/v1/molecule", tags=["molecule"])
    app.include_router(agent.router, prefix="/api/v1/agent", tags=["agent"])
    app.include_router(chem.router, prefix="/api/v1/chem", tags=["chem"])
    app.include_router(coref.router, prefix="/api/v1/coref", tags=["coref"])
    app.include_router(
        detection_cache.router, prefix="/api/v1/detection-cache", tags=["detection"]
    )
    app.include_router(notes.router, prefix="/api/v1/notes", tags=["notes"])
    app.include_router(settings.router, prefix="/api/v1/settings", tags=["settings"])
    # routers/text.py declares full paths (/text/chunk, /extract/activities, …)
    # so the include_router prefix is /api/v1 (mirrors health.router below).
    app.include_router(text.router, prefix="/api/v1", tags=["text"])
    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(resource.router, prefix="/api/v1", tags=["resource"])
    app.include_router(events.router, prefix="/api/v1/events", tags=["events"])
    app.include_router(pdf.router, prefix="/api/v1/pdf", tags=["pdf"])
    app.include_router(sar.router, prefix="/api/v1/sar", tags=["sar"])
    app.include_router(ocr.router, prefix="/api/v1/ocr", tags=["ocr"])
    app.include_router(
        diagnostics.router, prefix="/api/v1/diagnostics", tags=["diagnostics"]
    )
    # Moldet (FT detector) is mounted directly on the main app at /api/v1/moldet
    # so its endpoints are reachable at the documented paths (not nested under
    # the model_server mount at /api/v1/models).
    from .routers.moldet_api import router as moldet_router

    app.include_router(moldet_router, prefix="/api/v1/moldet", tags=["moldet"])

    # Mount existing model server endpoints under /api/v1/models/*
    from .server import app as model_server

    app.mount("/api/v1/models", model_server)

    # Serve React frontend in production
    # Priority: FRONTEND_DIST env (Docker) > sys._MEIPASS (PyInstaller) > dev path
    _env_dist = os.environ.get("FRONTEND_DIST")
    if _env_dist:
        frontend_dist = Path(_env_dist)
    elif getattr(sys, "frozen", False):
        frontend_dist = Path(sys._MEIPASS) / "frontend" / "dist"
    else:
        frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount(
            "/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend"
        )
        logger.info("Frontend: %s", frontend_dist)

    return app


app = create_app()
