"""Tool execution router — Python-side fallback for Rust Agent tools.

The Rust executor (`src-tauri/src/core/executor/mod.rs`) POSTs to
`/api/v1/tools/call` when a tool has no native Rust implementation.
This router provides a minimal stub that returns a clear message so the
Agent can inform the user rather than crashing with a 404.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ToolCallRequest(BaseModel):
    tool: str
    args: dict[str, Any]
    project_root: str | None = None


class ToolCallResponse(BaseModel):
    success: bool
    result: str
    error: str | None = None


@router.post("/call")
def call_tool(req: ToolCallRequest) -> ToolCallResponse:
    """Execute a tool by name (stub — returns informative fallback).

    Called by Rust:
      - src-tauri/src/core/executor/mod.rs::execute_sidecar
    """
    return ToolCallResponse(
        success=False,
        result="",
        error=f"Tool '{req.tool}' is not implemented in the Python sidecar. "
        "Please implement it in Rust or add a handler here.",
    )
