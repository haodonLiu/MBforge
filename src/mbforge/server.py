"""MBForge Model Server — FastAPI app with fixed local model backends.

Python sidecar hosts local models:
    - MolScribe         (backends.molscribe)
    - MolDet            (backends.moldet)

All API-based models (OpenAI, Anthropic, etc.) are called directly.
Knowledge base uses OpenKB + PageIndex (vectorless, reasoning-based).
"""

from __future__ import annotations

import asyncio
import inspect
import time
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .backends import moldet, molscribe
from .routers.health_router import router as health_router
from .routers.models_router import router as models_router
from .routers.moldet_api import router as moldet_router
from .routers.molscribe_api import router as molscribe_router
from .routers.pdf_render import router as pdf_render_router
from .server_state import (
    set_model_status,
)
from .utils.helpers import (
    ModelNotAvailableError,
    ValidationError,
)
from .utils.logger import get_logger

logger = get_logger("mbforge.server")

# ---------------------------------------------------------------------------
# Backend registry
# ---------------------------------------------------------------------------
_BACKENDS = [molscribe, moldet]


def _prewarm() -> None:
    pass  # MolDet/MolScribe are lazy-loaded on first use


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .utils.helpers import check_environment, shutdown_backends

    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, check_environment)
    loop.run_in_executor(None, _prewarm)
    try:
        yield
    finally:
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
        logger.info("Sidecar shutdown complete")


app = FastAPI(title="MBForge Model Server", version="1.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# with_model_status decorator
# ---------------------------------------------------------------------------

def with_model_status(model_id: str):
    """Decorator: parse request body, handle exceptions, set model status."""

    def decorator(fn):
        @wraps(fn)
        async def wrapper(request: Request) -> dict[str, Any]:
            try:
                body = await request.json()
            except Exception as e:
                raise ValidationError(f"Invalid JSON body: {e}") from e
            try:
                return await fn(request, body)
            except (ValidationError, ModelNotAvailableError):
                raise
            except Exception as e:
                set_model_status(model_id, "error")
                raise ModelNotAvailableError(str(e)) from e

        wrapper.__signature__ = inspect.signature(wrapper, follow_wrapped=False)
        del wrapper.__wrapped__
        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(ModelNotAvailableError)
async def _model_error_handler(
    request: Request, exc: ModelNotAvailableError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.message, "error_code": exc.error_code},
    )


@app.exception_handler(Exception)
async def _generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error on %s: %s", request.url.path, exc, exc_info=True)
    error_msg = "Internal server error"
    if isinstance(exc, (ValueError, KeyError)):
        error_msg = str(exc)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": error_msg, "error_code": "internal_error"},
    )


# ---------------------------------------------------------------------------
# Register routers
# ---------------------------------------------------------------------------

app.include_router(moldet_router, prefix="/api/v1/moldet", tags=["moldet"])
app.include_router(molscribe_router, prefix="/api/v1/molscribe", tags=["molscribe"])
app.include_router(pdf_render_router, prefix="/api/v1/pdf", tags=["pdf"])
app.include_router(models_router, prefix="/api/v1", tags=["models"])
app.include_router(health_router, prefix="/api/v1", tags=["health"])


# ---------------------------------------------------------------------------
# Test model endpoint (complex, kept here due to shared dependencies)
# ---------------------------------------------------------------------------

def _test_loading_sync(resource_id: str, subpath: str | None) -> dict[str, Any]:
    """Test model by loading and running minimal inference."""
    start = time.perf_counter()
    try:
        if resource_id == "moldet":
            from .backends.moldet import MolDetv2DocDetector
            detector = MolDetv2DocDetector()
            if not detector.is_available():
                return {"ok": False, "error": "Model not loaded", "duration_ms": 0}
            import numpy as np
            _ = detector.detect(np.zeros((640, 640, 3), dtype=np.uint8))
        elif resource_id == "molscribe":
            from .backends.molscribe import load as load_molscribe
            load_molscribe()
        else:
            return {"ok": False, "error": f"Unknown model: {resource_id}", "duration_ms": 0}

        duration_ms = int((time.perf_counter() - start) * 1000)
        return {"ok": True, "error": "", "duration_ms": duration_ms}
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.error("Model test failed for %s: %s", resource_id, e)
        return {"ok": False, "error": str(e), "duration_ms": duration_ms}


@app.post("/api/v1/test/model")
async def test_model(request: Request) -> dict[str, Any]:
    """Test a model by loading and running inference."""
    try:
        body = await request.json()
    except Exception as e:
        raise ValidationError("Invalid JSON body") from e

    model_id = body.get("model_id", "")
    subpath = body.get("subpath")
    if not model_id:
        raise ValidationError("model_id required")

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _test_loading_sync, model_id, subpath)
    return {"success": True, **result}
