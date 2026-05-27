"""Agent 对话路由."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...agent.agent import ProjectAgent
from ...core.project import Project
from ...core.memory import ProjectMemory
from ...utils.constants import PROJECT_META_DIR
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


def _get_chat_history_path(project_root: str) -> Path:
    """Get chat history file path."""
    return Path(project_root) / PROJECT_META_DIR / "memory" / "chat_history.json"


def _load_chat_history(project_root: str) -> list[dict]:
    """Load chat history from disk."""
    path = _get_chat_history_path(project_root)
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_chat_history(project_root: str, messages: list[dict]) -> None:
    """Save chat history to disk."""
    path = _get_chat_history_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)


@router.get("/history")
async def get_chat_history(project_root: str) -> dict:
    """Load chat history for a project."""
    if not project_root:
        return {"success": True, "messages": []}
    messages = _load_chat_history(project_root)
    return {"success": True, "messages": messages}


@router.post("/chat")
async def agent_chat(request: Request) -> dict:
    try:
        body = await request.json()
        messages = body.get("messages", [])

        if not messages:
            raise ValidationError("messages array is required")

        project_root_str = body.get("project_root", "")
        llm = get_llm(None)
        project = _get_project(project_root_str)
        project_root = Path(project.root) if project else None
        agent = ProjectAgent(llm=llm, project_root=project_root)
        user_input = _extract_last_user_message(messages)

        response = agent.chat(user_input)

        # Persist conversation
        if project_root_str:
            history = _load_chat_history(project_root_str)
            # Add new messages
            for msg in messages:
                if not any(h.get("id") == msg.get("id") for h in history):
                    history.append(msg)
            # Add assistant response
            history.append({
                "id": f"assistant_{datetime.now().timestamp()}",
                "role": "assistant",
                "content": response,
                "timestamp": datetime.now().isoformat(),
            })
            _save_chat_history(project_root_str, history)

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

            llm = get_llm(None)
            project = _get_project(project_root_str)
            project_root = Path(project.root) if project else None
            agent = ProjectAgent(llm=llm, project_root=project_root)
            user_input = _extract_last_user_message(messages)

            full_response = ""
            for chunk in agent.chat_stream(user_input):
                full_response += chunk
                yield f"data: {json.dumps({'delta': chunk})}\n\n"
            yield f"data: {json.dumps({'delta': '', 'finish_reason': 'stop'})}\n\n"

            # Persist conversation
            if project_root_str:
                history = _load_chat_history(project_root_str)
                for msg in messages:
                    if not any(h.get("id") == msg.get("id") for h in history):
                        history.append(msg)
                history.append({
                    "id": f"assistant_{datetime.now().timestamp()}",
                    "role": "assistant",
                    "content": full_response,
                    "timestamp": datetime.now().isoformat(),
                })
                _save_chat_history(project_root_str, history)
        except Exception as e:
            logger.error(f"Agent stream failed: {e}", exc_info=True)
            yield f"data: {json.dumps({'delta': '', 'finish_reason': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
