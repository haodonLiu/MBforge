"""SSE event stream endpoints."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()


@router.get("/stream")
async def event_stream() -> StreamingResponse:
    """Global SSE event stream for all real-time updates."""

    async def generate():
        while True:
            # TODO: subscribe to internal event bus and yield events
            await asyncio.sleep(5)
            yield f"data: {json.dumps({'type': 'heartbeat', 'ts': 0})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
