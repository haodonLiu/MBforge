"""Health check and environment status endpoints."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter

from ..utils.logger import get_logger

logger = get_logger("mbforge.health_router")

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": int(time.time()),
        "version": "0.4.0",
    }


@router.get("/environment/check")
async def environment_check() -> dict[str, Any]:
    """Check environment and resource status."""
    try:
        from ..core.resource_manager import ResourceManager

        report = ResourceManager.check_all()
        return {
            "status": "ok",
            "summary": report.summary,
            "resources": [
                {
                    "id": r.id,
                    "name": r.name,
                    "status": r.status.value,
                    "local_path": r.local_path,
                }
                for r in report.resources
            ],
        }
    except Exception as e:
        logger.error("Environment check failed: %s", e)
        return {
            "status": "error",
            "error": str(e),
            "resources": [],
        }
