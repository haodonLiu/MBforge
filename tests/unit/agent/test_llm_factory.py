"""Unit tests for the agent LLM factory."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from mbforge.agent.llm_factory import create_llm


@pytest.fixture
def fake_config_no_key(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Return a config with provider=ollama and no API key."""
    cfg = MagicMock()
    cfg.llm.provider = "ollama"
    cfg.llm.api_key = ""
    cfg.llm.base_url = ""
    cfg.llm.model = "llama3.1"
    cfg.llm.temperature = 0.5
    cfg.llm.max_tokens = 2048
    cfg.llm.request_timeout = 120
    monkeypatch.setattr("mbforge.agent.llm_factory.load_global_config", lambda: cfg)
    return cfg


@pytest.mark.asyncio
async def test_create_llm_ollama_does_not_require_api_key(
    fake_config_no_key: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ollama provider creates a ChatOpenAI instance without a real API key."""
    captured: dict[str, Any] = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("langchain_openai.ChatOpenAI", _FakeChatOpenAI)

    create_llm()

    assert captured["model"] == "llama3.1"
    assert captured["base_url"] == "http://localhost:11434/v1"
    assert captured["api_key"] == "ollama"
    assert captured["timeout"] == 120


@pytest.mark.asyncio
async def test_create_llm_openai_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI-compatible providers still require an API key."""
    cfg = MagicMock()
    cfg.llm.provider = "openai"
    cfg.llm.api_key = ""
    cfg.llm.base_url = ""
    cfg.llm.model = "gpt-4o-mini"
    cfg.llm.temperature = 0.7
    cfg.llm.max_tokens = 4096
    cfg.llm.request_timeout = 60
    monkeypatch.setattr("mbforge.agent.llm_factory.load_global_config", lambda: cfg)
    monkeypatch.setattr("langchain_openai.ChatOpenAI", lambda **kwargs: MagicMock())

    with pytest.raises(ValueError, match="api_key required"):
        create_llm()


@pytest.mark.asyncio
async def test_create_llm_passes_request_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The configured request_timeout is forwarded to the LangChain client."""
    cfg = MagicMock()
    cfg.llm.provider = "openai"
    cfg.llm.api_key = "sk-test"
    cfg.llm.base_url = "https://api.openai.com/v1"
    cfg.llm.model = "gpt-4o-mini"
    cfg.llm.temperature = 0.7
    cfg.llm.max_tokens = 4096
    cfg.llm.request_timeout = 90
    monkeypatch.setattr("mbforge.agent.llm_factory.load_global_config", lambda: cfg)

    captured: dict[str, Any] = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("langchain_openai.ChatOpenAI", _FakeChatOpenAI)

    create_llm()

    assert captured["timeout"] == 90
