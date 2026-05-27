"""Structured error response utilities for model_server."""

from __future__ import annotations

from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error response body."""

    success: bool = False
    error: str
    error_code: str = ""


def error_response(
    status_code: int,
    message: str,
    error_code: str = "",
) -> JSONResponse:
    """Build a structured JSON error response."""
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error=message,
            error_code=error_code,
        ).model_dump(),
    )
