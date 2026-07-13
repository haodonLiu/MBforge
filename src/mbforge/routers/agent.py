"""Agent chat endpoints with SSE streaming — LangGraph implementation."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..utils.config import load_global_config
from ..utils.logger import get_logger

logger = get_logger("mbforge.agent_router")

router = APIRouter()

# Cap session history to avoid unbounded memory growth in long conversations.
_MAX_HISTORY_MESSAGES = 50


@dataclass
class AgentState:
    """Encapsulates agent components to avoid module-level mutable globals."""

    llm: Any = None
    agent: Any = None
    tools: Any = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def ensure_initialized(self) -> None:
        """Lazy-initialize agent components (async-safe)."""
        if self.agent is not None:
            return
        async with self.lock:
            if self.agent is not None:
                return
            try:
                llm_config = load_global_config().llm
                if not llm_config.api_key:
                    logger.info("No LLM API key configured — agent running in stub mode")
                    return

                from ..agent.graph import create_agent
                from ..agent.llm_factory import create_llm_from_settings
                from ..agent.tools import get_all_tools

                self.llm = create_llm_from_settings()
                self.tools = get_all_tools()
                self.agent = create_agent(self.llm, self.tools)
                logger.info("Agent initialized successfully")
            except Exception as e:
                logger.warning("Agent init failed (stub mode): %s", e)
                self.agent = None

    def reset(self) -> None:
        """Reset agent state."""
        self.llm = None
        self.agent = None
        self.tools = None


# Single instance — replaces the three module-level globals
_agent_state = AgentState()


def _make_agent_config(library_root: str | None) -> dict[str, Any]:
    """Build the LangGraph config that carries ``library_root`` into tools."""
    return {"configurable": {"library_root": library_root or ""}}


def _trim_history(messages: list) -> None:
    """Trim the in-place message list to the most recent history cap."""
    while len(messages) > _MAX_HISTORY_MESSAGES:
        messages.pop(0)


@router.post("/init")
async def agent_init() -> dict:
    try:
        from ..agent.sessions import session_store

        session_store.clear_all()
        _agent_state.reset()
        await _agent_state.ensure_initialized()
        return {"success": True, "agent_ready": _agent_state.agent is not None}
    except Exception as e:
        logger.error("Agent init error: %s", e)
        return {"success": True, "agent_ready": False, "warning": str(e)}


@router.post("/session")
async def agent_create_session(body: dict) -> dict:
    try:
        import uuid

        from ..agent.sessions import session_store

        sid = body.get("session_id", str(uuid.uuid4()))
        session_store.create(sid, body.get("library_root"))
        return {"success": True, "session_id": sid}
    except Exception as e:
        logger.error("Session create error: %s", e)
        return {"success": False, "error": str(e)}


@router.delete("/session/{session_id}")
async def agent_destroy_session(session_id: str) -> dict:
    from ..agent.sessions import session_store

    session_store.delete(session_id)
    return {"success": True}


@router.post("/session/{session_id}/clear")
async def agent_clear(session_id: str) -> dict:
    from ..agent.sessions import session_store

    session_store.clear(session_id)
    return {"success": True}


@router.get("/session/{session_id}/history")
async def agent_get_history(session_id: str) -> dict:
    try:
        from ..agent.sessions import session_store

        session = session_store.get(session_id)
        if not session:
            return {"success": False, "messages": []}
        messages = [{"role": m.role, "content": m.content} for m in session.messages]
        return {"success": True, "messages": messages}
    except Exception as e:
        logger.error("History error: %s", e)
        return {"success": False, "error": str(e)}


@router.post("/session/{session_id}/chat")
async def agent_chat(session_id: str, body: dict) -> dict:
    try:
        from ..agent.sessions import ChatMessage, session_store

        session = session_store.get(session_id)
        if not session:
            return {"success": False, "error": "session not found"}
        user_input = body.get("user_input", "")
        if not user_input.strip():
            return {"success": False, "error": "empty input"}

        session.messages.append(ChatMessage(role="user", content=user_input))
        _trim_history(session.messages)

        await _agent_state.ensure_initialized()
        if _agent_state.agent is not None:
            try:
                lc_messages = [
                    {"role": m.role, "content": m.content} for m in session.messages
                ]
                response = await _agent_state.agent.ainvoke(
                    {"messages": lc_messages},
                    config=_make_agent_config(session.library_root),
                )
                reply = (
                    response["messages"][-1].content if response.get("messages") else ""
                )
            except Exception as e:
                logger.error("Agent invoke failed: %s", e)
                reply = "[Agent error]"
        else:
            reply = f"[Agent stub] Received: {user_input}"

        session.messages.append(ChatMessage(role="assistant", content=reply))
        _trim_history(session.messages)
        return {"success": True, "reply": reply}
    except Exception as e:
        logger.error("Agent chat error: %s", e)
        return {"success": False, "error": str(e)}


@router.get("/session/{session_id}/chat/stream")
async def agent_chat_stream(session_id: str, user_input: str = "") -> StreamingResponse:
    """SSE streaming chat with LangGraph agent."""
    from ..agent.sessions import ChatMessage, session_store

    session = session_store.get(session_id)
    if not session:
        return StreamingResponse(
            iter([f"data: {json.dumps({'error': 'session not found'})}\n\n"]),
            media_type="text/event-stream",
        )

    await _agent_state.ensure_initialized()

    async def event_stream():
        session.messages.append(ChatMessage(role="user", content=user_input))
        _trim_history(session.messages)

        if _agent_state.agent is not None:
            try:
                from ..agent.graph import stream_agent_response

                lc_messages = [
                    {"role": m.role, "content": m.content} for m in session.messages
                ]
                full_reply = ""
                async for event in stream_agent_response(
                    _agent_state.agent,
                    lc_messages,
                    config=_make_agent_config(session.library_root),
                ):
                    if event["type"] == "chunk":
                        content = event.get("content", "")
                        full_reply += content
                        yield f"data: {json.dumps({'session_id': session_id, 'delta': content, 'event': 'chunk'})}\n\n"
                    elif event["type"] == "tool_call":
                        yield f"data: {json.dumps({'session_id': session_id, 'event': 'tool_call', 'tool': event.get('tool', '')})}\n\n"
                    elif event["type"] == "tool_result":
                        yield f"data: {json.dumps({'session_id': session_id, 'event': 'tool_result', 'output': event.get('output', '')[:200]})}\n\n"
                    elif event["type"] == "error":
                        error_msg = event.get("error", "[Agent error]")
                        recoverable = event.get("recoverable", False)
                        yield f"data: {json.dumps({'session_id': session_id, 'event': 'error', 'error': error_msg, 'recoverable': recoverable})}\n\n"

                if not full_reply:
                    full_reply = "[No response from agent]"
                session.messages.append(
                    ChatMessage(role="assistant", content=full_reply)
                )
                _trim_history(session.messages)
            except Exception as e:
                logger.error("Agent streaming error: %s", e)
                error_msg = "[Agent error]"
                session.messages.append(
                    ChatMessage(role="assistant", content=error_msg)
                )
                yield f"data: {json.dumps({'session_id': session_id, 'delta': error_msg, 'event': 'chunk'})}\n\n"
        else:
            reply = f"[Agent stub] {user_input}"
            for i in range(0, len(reply), 24):
                chunk = reply[i : i + 24]
                yield f"data: {json.dumps({'session_id': session_id, 'delta': chunk, 'event': 'chunk'})}\n\n"
                await asyncio.sleep(0.02)
            session.messages.append(ChatMessage(role="assistant", content=reply))

        yield f"data: {json.dumps({'session_id': session_id, 'event': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
