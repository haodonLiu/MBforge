from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from mbforge.routers import agent as agent_module
from mbforge.routers.agent import _agent_state, _make_agent_config, _trim_history


@pytest.fixture(autouse=True)
def _reset_agent_state():
    """Reset the global agent state before and after each test."""
    _agent_state.reset()
    yield
    _agent_state.reset()


@pytest.mark.asyncio
async def test_agent_state_concurrent_init_creates_single_agent(monkeypatch):
    """Concurrent first calls to AgentState.ensure_initialized create one agent."""
    call_count = 0

    def _fake_create_agent(llm, tools):
        nonlocal call_count
        call_count += 1
        return f"agent-{call_count}"

    fake_cfg = MagicMock()
    fake_cfg.llm.api_key = "test-key"

    monkeypatch.setattr(agent_module, "load_global_config", lambda: fake_cfg)
    monkeypatch.setattr("mbforge.agent.llm_factory.create_llm_from_settings", lambda: "llm")
    monkeypatch.setattr("mbforge.agent.tools.get_all_tools", lambda: ["tool"])
    monkeypatch.setattr("mbforge.agent.graph.create_agent", _fake_create_agent)

    async def _init():
        await _agent_state.ensure_initialized()
        return _agent_state.agent

    agents = await asyncio.gather(*(_init() for _ in range(8)))

    assert len(set(agents)) == 1
    assert all(a == "agent-1" for a in agents)
    assert call_count == 1


def test_make_agent_config_carries_library_root() -> None:
    """The router builds a LangGraph config with the session's library_root."""
    assert _make_agent_config("/tmp/lib") == {
        "configurable": {"library_root": "/tmp/lib"}
    }
    assert _make_agent_config(None) == {"configurable": {"library_root": ""}}


def test_trim_history_keeps_recent_messages() -> None:
    """History trimming drops the oldest messages once the cap is exceeded."""
    messages = [{"role": "user", "content": f"msg-{i}"} for i in range(60)]
    _trim_history(messages)
    assert len(messages) == 50
    assert messages[0]["content"] == "msg-10"
    assert messages[-1]["content"] == "msg-59"


@pytest.mark.asyncio
async def test_agent_chat_passes_library_root_config(monkeypatch) -> None:
    """The chat endpoint invokes the agent with the session's library_root config."""
    from mbforge.agent.sessions import session_store

    session_store.create("s1", library_root="/tmp/chat-lib")

    captured: dict = {}

    class _FakeAgent:
        async def ainvoke(self, input, config=None):
            captured["config"] = config
            return {"messages": [MagicMock(content="hi")]}

    _agent_state.agent = _FakeAgent()

    response = await agent_module.agent_chat(
        "s1", {"user_input": "hello"}
    )

    assert response["success"] is True
    assert captured["config"] == {
        "configurable": {"library_root": "/tmp/chat-lib"}
    }
    session = session_store.get("s1")
    assert session.messages[-1].content == "hi"


@pytest.mark.asyncio
async def test_agent_chat_stream_emits_error_event(monkeypatch) -> None:
    """The streaming endpoint forwards agent error events as SSE error events."""
    from mbforge.agent.sessions import session_store

    session_store.create("s2", library_root="/tmp/stream-lib")

    async def _fake_stream(*args, **kwargs):
        yield {"type": "error", "error": "model timeout", "recoverable": True}
        yield {"type": "done"}

    _agent_state.agent = MagicMock()
    monkeypatch.setattr("mbforge.agent.graph.stream_agent_response", _fake_stream)

    response = await agent_module.agent_chat_stream("s2", user_input="hello")
    body = "".join([chunk async for chunk in response.body_iterator])

    assert '"event": "error"' in body
    assert '"error": "model timeout"' in body
    assert '"recoverable": true' in body
