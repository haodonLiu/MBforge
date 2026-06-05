"""LLM 推理路由."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette.requests import ClientDisconnect

from mbforge.models.base import Message, run_sync_async

from ...utils.exceptions import ModelNotAvailableError
from ...utils.logger import get_logger
from ..models.llm import get_llm
from .health import set_model_status

logger = get_logger(__name__)
router = APIRouter()


@router.post("/chat")
async def chat(request: Request) -> dict[str, Any]:
    # 读取跨语言 trace 上下文（来自 Rust 端 observability 层）
    trace_id = request.headers.get("X-Trace-Id")
    span_id = request.headers.get("X-Span-Id")
    if trace_id:
        logger.info(f"[trace={trace_id} span={span_id}] LLM chat started")
    try:
        body = await request.json()
        messages = [Message(**m) for m in body.get("messages", [])]
        temperature = body.get("temperature", 0.7)
        max_tokens = body.get("max_tokens", 4096)

        llm = get_llm(None)
        result = await run_sync_async(
            llm.chat, messages, temperature=temperature, max_tokens=max_tokens
        )
        set_model_status("llm", "ready")
        if trace_id:
            logger.info(f"[trace={trace_id} span={span_id}] LLM chat done")
        return {"content": result, "finish_reason": "stop"}
    except Exception as e:
        set_model_status("llm", "error")
        log_extra = f" trace={trace_id}" if trace_id else ""
        logger.error(f"LLM chat failed{log_extra}: {e}", exc_info=True)
        raise ModelNotAvailableError(str(e)) from e


@router.post("/chat-stream")
async def chat_stream(request: Request) -> StreamingResponse:
    trace_id = request.headers.get("X-Trace-Id")
    span_id = request.headers.get("X-Span-Id")
    if trace_id:
        logger.info(f"[trace={trace_id} span={span_id}] LLM stream started")
    async def event_generator():
        try:
            body = await request.json()
            messages = [Message(**m) for m in body.get("messages", [])]
            temperature = body.get("temperature", 0.7)
            max_tokens = body.get("max_tokens", 4096)

            llm = get_llm(None)
            async for chunk in llm.achat_stream(messages, temperature=temperature, max_tokens=max_tokens):
                yield f"data: {json.dumps({'delta': chunk.delta, 'finish_reason': chunk.finish_reason})}\n\n"
            set_model_status("llm", "ready")
        except ClientDisconnect:
            logger.debug("Client disconnected during LLM stream")
        except Exception as e:
            log_extra = f" trace={trace_id}" if trace_id else ""
            logger.error(f"LLM stream failed{log_extra}: {e}", exc_info=True)
            yield f"data: {json.dumps({'delta': '', 'finish_reason': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
