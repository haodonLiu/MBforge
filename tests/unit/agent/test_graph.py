"""Unit tests for the LangGraph agent streaming wrapper."""

from __future__ import annotations

from typing import Any

import pytest

from mbforge.agent.graph import stream_agent_response


@pytest.mark.asyncio
async def test_stream_agent_response_yields_error_event_on_fatal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fatal streaming errors are surfaced as SSE error events, not re-raised."""

    class _FakeAgent:
        async def astream_events(self, *args, **kwargs):
            raise RuntimeError("boom")
            yield  # make it an async generator

    events = []
    async for event in stream_agent_response(_FakeAgent(), []):
        events.append(event)

    assert events[0] == {"type": "error", "error": "Internal error", "recoverable": False}
    assert events[-1] == {"type": "done"}


@pytest.mark.asyncio
async def test_stream_agent_response_yields_error_event_for_recoverable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool/LLM provider errors are emitted as recoverable error events."""
    from mbforge.agent.graph import LLMProviderError

    class _FakeAgent:
        async def astream_events(self, *args, **kwargs):
            raise LLMProviderError("provider down")
            yield  # make it an async generator

    events = []
    async for event in stream_agent_response(_FakeAgent(), []):
        events.append(event)

    assert events[0] == {
        "type": "error",
        "error": "provider down",
        "recoverable": True,
    }
    assert events[-1] == {"type": "done"}


@pytest.mark.asyncio
async def test_stream_agent_response_passes_config_to_agent() -> None:
    """The supplied config is forwarded to the agent's astream_events call."""
    passed_config: dict[str, Any] | None = None

    class _FakeAgent:
        async def astream_events(self, input, config=None, **kwargs):
            nonlocal passed_config
            passed_config = config
            if False:
                yield  # make it an async generator

    config = {"configurable": {"library_root": "/tmp/lib"}}
    async for _ in stream_agent_response(_FakeAgent(), [], config=config):
        pass

    assert passed_config == config
