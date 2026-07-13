from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from mbforge.routers import agent as agent_module
from mbforge.routers.agent import _agent_state


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
