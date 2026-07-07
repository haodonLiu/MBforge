"""Diagnostics router — surface error ring buffer + ingest client-side errors.

Three read endpoints query the in-process ring buffer (see utils/logger.py).
The write endpoint accepts batches of client-side errors thrown into the
front-end ErrorBoundary, mirrored back into the same buffer so operators get
a unified view from `/api/v1/diagnostics/errors`.

Why a single process-wide ring buffer: errors need to be inspectable while
the system is still running. Persisting to SQLite would force a migration to
inspect, defeating the "users-look-at-it-when-stuck" use case.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from ..utils.logger import (
    get_diagnostic_by_id,
    get_diagnostic_stats,
    get_diagnostics,
    push_diagnostic,
)

logger = logging.getLogger("mbforge.routers.diagnostics")

router = APIRouter()


class ClientErrorItem(BaseModel):
    message: str
    name: str | None = None
    stack: str | None = None
    category: str | None = "client"
    severity: str | None = "ERROR"
    context: dict[str, Any] = Field(default_factory=dict)
    timestamp: float | None = None


class ClientErrorBatch(BaseModel):
    errors: list[ClientErrorItem] = Field(default_factory=list)


@router.get("/errors")
async def list_errors(
    since: int | None = Query(default=None, ge=0),
    level: str | None = Query(default=None),
    category: str | None = Query(default=None),
    error_code: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    """List recent diagnostic records, optionally filtered."""
    records = get_diagnostics(
        since=since,
        level=level,
        category=category,
        error_code=error_code,
        limit=limit,
    )
    return {"count": len(records), "errors": records}


@router.get("/errors/{seq_id}")
async def get_error(seq_id: int) -> dict[str, Any]:
    """Look up a single diagnostic record by seq, or 404."""
    rec = get_diagnostic_by_id(seq_id)
    if rec is None:
        return {"success": False, "error": "not found", "seq": seq_id}
    return rec


@router.get("/stats")
async def stats() -> dict[str, Any]:
    """Aggregate counts — by level, category, error_code, total."""
    return get_diagnostic_stats()


@router.post("/errors", status_code=status.HTTP_204_NO_CONTENT)
async def report_client_error(batch: ClientErrorBatch) -> None:
    """Ingest a batch of front-end caught errors.

    Each item is pushed into the same ring buffer used by the backend
    exception handler, tagged with `category: client`. Returns 204 with no
    body — clients should treat the call as fire-and-forget.
    """
    for item in batch.errors:
        push_diagnostic(
            {
                "level": (item.severity or "ERROR").upper(),
                "logger": "mbforge.client.errorboundary",
                "message": item.message,
                "exception": item.stack,
                "category": item.category or "client",
                "severity": (item.severity or "ERROR").lower(),
                "error_code": "client_boundary_error",
                "status_code": 0,
                "context": item.context,
            }
        )
