"""LLM factory — creates LangChain chat models from global settings.

Supports: openai, anthropic, ollama, openai_compatible.

Business LLM settings come from ``AppConfig.llm`` (the Settings UI persists it
to ``settings.json``). Explicit function arguments remain available for
callers that intentionally need a one-off override.
"""

from __future__ import annotations

from typing import Any

from ..utils.config import load_global_config
from ..utils.logger import get_logger

logger = get_logger("mbforge.agent.llm_factory")


def _resolve_provider(arg: str, cfg_provider: str) -> str:
    return arg or cfg_provider or "openai_compatible"


def _resolve_api_key(arg: str, cfg_key: str) -> str:
    """Resolve an explicit API key or the persisted LLM setting."""
    return arg or cfg_key


def _resolve_base_url(arg: str, cfg_url: str) -> str:
    return arg or cfg_url or "https://api.openai.com/v1"


def _resolve_model(arg: str, cfg_model: str, default: str) -> str:
    return arg or cfg_model or default


def create_llm(
    provider: str = "",
    model: str = "",
    api_key: str = "",
    base_url: str = "",
    **kwargs: Any,
) -> Any:
    """Create a LangChain chat model.

    Priority: explicit args > AppConfig.llm > defaults.
    """
    llm_cfg = load_global_config().llm
    provider = _resolve_provider(provider, llm_cfg.provider)

    if provider in ("openai_compatible", "openai", "deepseek", "ollama"):
        api_key = _resolve_api_key(api_key, llm_cfg.api_key)
        if not api_key:
            raise ValueError(
                "api_key required for OpenAI-compatible provider (set via Settings UI)"
            )
        base_url = _resolve_base_url(base_url, llm_cfg.base_url)
        model = _resolve_model(model, llm_cfg.model, "gpt-3.5-turbo")
        temperature = kwargs.get("temperature", llm_cfg.temperature)
        max_tokens = kwargs.get("max_tokens", llm_cfg.max_tokens)

        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    elif provider == "anthropic":
        api_key = _resolve_api_key(api_key, llm_cfg.api_key)
        if not api_key:
            raise ValueError(
                "api_key required for Anthropic provider (set via Settings UI)"
            )
        model = _resolve_model(model, llm_cfg.model, "claude-3-sonnet-20240229")
        temperature = kwargs.get("temperature", llm_cfg.temperature)
        max_tokens = kwargs.get("max_tokens", llm_cfg.max_tokens)

        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def create_llm_from_settings() -> Any:
    """Create an LLM from the persisted global settings.

    Used by ``routers/agent.py`` lazy initialization.
    """
    return create_llm()
