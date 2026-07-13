"""Regression tests for persisted business LLM configuration."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mbforge.agent import llm_factory
from mbforge.routers.agent import AgentState
from mbforge.utils.config import LLMConfig


def test_create_llm_does_not_fall_back_to_environment_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An obsolete environment key must not bypass an empty Settings UI value."""
    monkeypatch.setenv("MBFORGE_LLM_API_KEY", "legacy-environment-key")
    monkeypatch.setattr(
        llm_factory,
        "load_global_config",
        lambda: SimpleNamespace(llm=LLMConfig(api_key="")),
    )

    with pytest.raises(ValueError, match="set via Settings UI"):
        llm_factory.create_llm()


def test_agent_state_uses_persisted_api_key_to_choose_stub_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Agent startup must ignore a legacy environment key when settings are empty."""
    import mbforge.routers.agent as agent_router

    monkeypatch.setenv("MBFORGE_LLM_API_KEY", "legacy-environment-key")
    monkeypatch.setattr(
        agent_router,
        "load_global_config",
        lambda: SimpleNamespace(llm=LLMConfig(api_key="")),
    )

    state = AgentState()
    state.ensure_initialized()

    assert state.agent is None
    assert state.llm is None
    assert state.tools is None
