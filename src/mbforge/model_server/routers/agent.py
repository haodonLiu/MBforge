"""Agent 对话路由."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ...utils.exceptions import ModelNotAvailableError, ValidationError
from ...utils.logger import get_logger
from ..agent_manager import (
    chat,
    chat_stream,
    get_tool_executor,
    load_chat_history,
    save_chat_history,
)

logger = get_logger(__name__)
router = APIRouter()


def _extract_last_user_message(messages: list[dict]) -> str:
    """Extract the last user message from a messages array."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""


@router.get("/history")
async def get_chat_history(project_root: str) -> dict:
    """Load chat history for a project."""
    if not project_root:
        return {"success": True, "messages": []}
    messages = load_chat_history(project_root)
    return {"success": True, "messages": messages}


@router.post("/chat")
async def agent_chat(request: Request) -> dict:
    try:
        body = await request.json()
        messages = body.get("messages", [])

        if not messages:
            raise ValidationError("messages array is required")

        project_root_str = body.get("project_root", "")
        user_input = _extract_last_user_message(messages)

        response = chat(user_input, project_root_str, messages=messages)

        # Persist conversation
        if project_root_str:
            history = load_chat_history(project_root_str)
            for msg in messages:
                if not any(h.get("id") == msg.get("id") for h in history):
                    history.append(msg)
            history.append({
                "id": f"assistant_{datetime.now().timestamp()}",
                "role": "assistant",
                "content": response,
                "timestamp": datetime.now().isoformat(),
            })
            save_chat_history(project_root_str, history)

        return {"success": True, "content": response}
    except (ValidationError, ModelNotAvailableError):
        raise
    except Exception as e:
        logger.error(f"Agent chat failed: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e))


@router.post("/chat-stream")
async def agent_chat_stream(request: Request) -> StreamingResponse:
    async def event_generator():
        try:
            body = await request.json()
            messages = body.get("messages", [])
            project_root_str = body.get("project_root", "")

            user_input = _extract_last_user_message(messages)

            full_response = ""
            for chunk in chat_stream(user_input, project_root_str, messages=messages):
                full_response += chunk
                yield f"data: {json.dumps({'delta': chunk})}\n\n"
            yield f"data: {json.dumps({'delta': '', 'finish_reason': 'stop'})}\n\n"

            # Persist conversation
            if project_root_str:
                history = load_chat_history(project_root_str)
                for msg in messages:
                    if not any(h.get("id") == msg.get("id") for h in history):
                        history.append(msg)
                history.append({
                    "id": f"assistant_{datetime.now().timestamp()}",
                    "role": "assistant",
                    "content": full_response,
                    "timestamp": datetime.now().isoformat(),
                })
                save_chat_history(project_root_str, history)
        except Exception as e:
            logger.error(f"Agent stream failed: {e}", exc_info=True)
            yield f"data: {json.dumps({'delta': '', 'finish_reason': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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

        result = executor.registry.call(tool_name, args)
        return {"success": True, "result": result}
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Tool call failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
