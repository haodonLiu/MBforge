"""Agent 对话路由."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ...agent.agent import ProjectAgent
from ...core.project import Project
from ..models.llm import get_llm

router = APIRouter()


@router.post("/chat")
async def agent_chat(request: Request) -> dict:
    try:
        body = await request.json()
        project_root = body.get("project_root", "")
        messages = body.get("messages", [])
        temperature = body.get("temperature", 0.7)

        llm = get_llm(None)
        project = None
        if project_root:
            project = Project.open(Path(project_root))

        agent = ProjectAgent(llm=llm, project=project)
        # Extract last user message
        user_input = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_input = m.get("content", "")
                break

        response = agent.chat(user_input)
        return {"success": True, "content": response}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/chat-stream")
async def agent_chat_stream(request: Request) -> StreamingResponse:
    async def event_generator():
        try:
            body = await request.json()
            project_root = body.get("project_root", "")
            messages = body.get("messages", [])

            llm = get_llm(None)
            project = None
            if project_root:
                project = Project.open(Path(project_root))

            agent = ProjectAgent(llm=llm, project=project)
            # Extract last user message
            user_input = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    user_input = m.get("content", "")
                    break

            for chunk in agent.chat_stream(user_input):
                yield f"data: {json.dumps({'delta': chunk})}\n\n"
            yield f"data: {json.dumps({'delta': '', 'finish_reason': 'stop'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'delta': '', 'finish_reason': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
