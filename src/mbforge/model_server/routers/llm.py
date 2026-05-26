"""LLM 推理路由."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from mbforge.models.base import Message
from ..models.llm import get_llm
from .health import set_model_status

router = APIRouter()


@router.post("/chat")
async def chat(request: Request) -> dict:
    try:
        body = await request.json()
        messages = [Message(**m) for m in body.get("messages", [])]
        temperature = body.get("temperature", 0.7)
        max_tokens = body.get("max_tokens", 4096)

        llm = get_llm(None)
        result = llm.chat(messages, temperature=temperature, max_tokens=max_tokens)
        set_model_status("llm", "ready")
        return {"content": result, "finish_reason": "stop"}
    except Exception as e:
        set_model_status("llm", "error")
        return {"content": "", "finish_reason": "error", "error": str(e)}


@router.post("/chat-stream")
async def chat_stream(request: Request) -> StreamingResponse:
    async def event_generator():
        try:
            body = await request.json()
            messages = [Message(**m) for m in body.get("messages", [])]
            temperature = body.get("temperature", 0.7)
            max_tokens = body.get("max_tokens", 4096)

            llm = get_llm(None)
            for chunk in llm.chat_stream(messages, temperature=temperature, max_tokens=max_tokens):
                yield f"data: {json.dumps({'delta': chunk.delta, 'finish_reason': chunk.finish_reason})}\n\n"
            set_model_status("llm", "ready")
        except Exception as e:
            yield f"data: {json.dumps({'delta': '', 'finish_reason': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
