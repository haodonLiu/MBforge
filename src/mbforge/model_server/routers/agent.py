"""Agent 工具桥接路由 — 仅保留 /tools/call 端点供 Rust Agent sidecar 使用.

Agent 对话功能已迁移到 Rust Agent（src-tauri/src/core/agent.rs），
通过 Tauri invoke 调用。Python 端不再管理代理实例。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from ...utils.exceptions import ModelNotAvailableError, ValidationError
from ...utils.logger import get_logger
from ..agent_manager import get_tool_executor

logger = get_logger(__name__)
router = APIRouter()


@router.post("/tools/call")
async def call_tool(request: Request) -> dict:
    """统一工具调用端点 — Rust Agent 通过 HTTP 调用 Python 工具."""
    try:
        body = await request.json()
        tool_name = body.get("tool", "")
        args = body.get("args", {})
        project_root = body.get("project_root", "")

        if not tool_name:
            raise ValidationError("tool name is required")

        executor = get_tool_executor(project_root)
        if executor is None:
            return {"success": False, "error": "Tool executor not initialized. Open a project first."}

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: executor.registry.call(tool_name, args)
        )
        return {"success": True, "result": result}
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Tool call failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
