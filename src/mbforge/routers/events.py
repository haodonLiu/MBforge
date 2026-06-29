"""SSE event stream endpoints."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter()


@router.get("/stream")
async def event_stream() -> EventSourceResponse:
    """Global SSE event stream for all real-time updates."""

    async def generate():
        while True:
            await asyncio.sleep(30)
            yield {"event": "heartbeat", "data": json.dumps({"ts": 0})}

    return EventSourceResponse(generate())
