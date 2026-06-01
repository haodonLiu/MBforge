"""LLM 推理路由."""

from __future__ import annotations
from typing import Any

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette.requests import ClientDisconnect

from mbforge.models.base import Message
from ...utils.exceptions import ModelNotAvailableError
from ...utils.logger import get_logger
from ..models.llm import get_llm
from .health import set_model_status

logger = get_logger(__name__)
router = APIRouter()


@router.post("/chat")
async def chat(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
        messages = [Message(**m) for m in body.get("messages", [])]
        temperature = body.get("temperature", 0.7)
        max_tokens = body.get("max_tokens", 4096)

        llm = get_llm(None)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: llm.chat(messages, temperature=temperature, max_tokens=max_tokens)
        )
        set_model_status("llm", "ready")
        return {"content": result, "finish_reason": "stop"}
    except Exception as e:
        set_model_status("llm", "error")
        logger.error(f"LLM chat failed: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e))


@router.post("/chat-stream")
async def chat_stream(request: Request) -> StreamingResponse:
    async def event_generator():
        try:
            body = await request.json()
            messages = [Message(**m) for m in body.get("messages", [])]
            temperature = body.get("temperature", 0.7)
            max_tokens = body.get("max_tokens", 4096)

            llm = get_llm(None)
            loop = asyncio.get_running_loop()
            # Run the sync stream generator in a thread to avoid blocking the event loop
            def _sync_stream():
                return list(llm.chat_stream(messages, temperature=temperature, max_tokens=max_tokens))
            chunks = await loop.run_in_executor(None, _sync_stream)
            for chunk in chunks:
                yield f"data: {json.dumps({'delta': chunk.delta, 'finish_reason': chunk.finish_reason})}\n\n"
            set_model_status("llm", "ready")
        except ClientDisconnect:
            logger.debug("Client disconnected during LLM stream")
        except Exception as e:
            logger.error(f"LLM stream failed: {e}", exc_info=True)
            yield f"data: {json.dumps({'delta': '', 'finish_reason': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
