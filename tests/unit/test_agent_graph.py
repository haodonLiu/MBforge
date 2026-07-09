"""Tests for agent streaming error handling."""
import pytest

from mbforge.agent.graph import (
    LLMProviderError,
    ToolExecutionError,
    stream_agent_response,
)


async def _failing_agent(exc):
    async def _aiter():
        raise exc
        yield  # unreachable; makes _aiter an async generator

    class _FakeAgent:
        async def astream_events(self, *args, **kwargs):
            async for item in _aiter():
                yield item

    return _FakeAgent()


@pytest.mark.asyncio
async def test_recoverable_tool_error():
    agent = await _failing_agent(ToolExecutionError("tool failed"))
    events = [e async for e in stream_agent_response(agent, [])]
    errors = [e for e in events if e.get("type") == "error"]
    assert len(errors) == 1
    assert errors[0]["error"] == "tool failed"
    assert errors[0].get("recoverable") is True


@pytest.mark.asyncio
async def test_recoverable_llm_error():
    agent = await _failing_agent(LLMProviderError("llm failed"))
    events = [e async for e in stream_agent_response(agent, [])]
    errors = [e for e in events if e.get("type") == "error"]
    assert errors[0]["error"] == "llm failed"
    assert errors[0].get("recoverable") is True


@pytest.mark.asyncio
async def test_fatal_unknown_error():
    agent = await _failing_agent(RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        [e async for e in stream_agent_response(agent, [])]
