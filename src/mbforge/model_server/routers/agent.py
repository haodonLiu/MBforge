"""Agent 对话路由."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ...agent.agent import ProjectAgent
from ...core.project import Project
from ...utils.exceptions import ModelNotAvailableError, ValidationError
from ...utils.logger import get_logger
from ..models.llm import get_llm

logger = get_logger(__name__)
router = APIRouter()


def _extract_last_user_message(messages: list[dict]) -> str:
    """Extract the last user message from a messages array."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""


def _get_project(project_root: str) -> Project | None:
    """Open project if root is provided, return None otherwise."""
    if not project_root:
        return None
    return Project.open(Path(project_root))


@router.post("/chat")
async def agent_chat(request: Request) -> dict:
    try:
        body = await request.json()
        messages = body.get("messages", [])

        if not messages:
            raise ValidationError("messages array is required")

        llm = get_llm(None)
        project = _get_project(body.get("project_root", ""))
        agent = ProjectAgent(llm=llm, project=project)
        user_input = _extract_last_user_message(messages)

        response = agent.chat(user_input)
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

            llm = get_llm(None)
            project = _get_project(body.get("project_root", ""))
            agent = ProjectAgent(llm=llm, project=project)
            user_input = _extract_last_user_message(messages)

            for chunk in agent.chat_stream(user_input):
                yield f"data: {json.dumps({'delta': chunk})}\n\n"
            yield f"data: {json.dumps({'delta': '', 'finish_reason': 'stop'})}\n\n"
        except Exception as e:
            logger.error(f"Agent stream failed: {e}", exc_info=True)
            yield f"data: {json.dumps({'delta': '', 'finish_reason': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
