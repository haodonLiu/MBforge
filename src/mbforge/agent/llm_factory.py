"""LLM factory — creates LangChain chat models from config.

Supports: openai, anthropic, ollama, openai_compatible
"""

from __future__ import annotations

from typing import Any

from ..utils.config import load_global_config
from ..utils.logger import get_logger

logger = get_logger("mbforge.agent.llm_factory")


def create_llm(
    provider: str = "",
    model: str = "",
    api_key: str = "",
    base_url: str = "",
    **kwargs: Any,
) -> Any:
    """Create a LangChain chat model.

    Priority: explicit args > AppConfig > defaults.
    """
    cfg = load_global_config()
    provider = provider or "openai_compatible"

    if provider in ("openai_compatible", "openai", "deepseek", "ollama"):
        api_key = api_key or "sk-placeholder"
        base_url = base_url or "https://api.openai.com/v1"
        model = model or "gpt-3.5-turbo"
        temperature = kwargs.get("temperature", 0.2)
        max_tokens = kwargs.get("max_tokens", 8192)

        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    elif provider == "anthropic":
        api_key = api_key or "sk-placeholder"
        model = model or "claude-3-sonnet-20240229"
        temperature = kwargs.get("temperature", 0.2)
        max_tokens = kwargs.get("max_tokens", 8192)

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
    """Create LLM from global settings (Settings UI or env vars)."""
    import os

    provider = os.environ.get("MBFORGE_LLM_PROVIDER", "openai_compatible")
    model = os.environ.get("MBFORGE_LLM_MODEL", "gpt-3.5-turbo")
    api_key = os.environ.get("MBFORGE_LLM_API_KEY", "")
    base_url = os.environ.get("MBFORGE_LLM_BASE_URL", "https://api.openai.com/v1")

    if not api_key:
        cfg = load_global_config()
        # Try to get from config
        if hasattr(cfg, "llm"):
            llm_cfg = cfg.llm
            api_key = getattr(llm_cfg, "api_key", "") or api_key
            base_url = getattr(llm_cfg, "base_url", "") or base_url
            model = getattr(llm_cfg, "model", "") or model

    return create_llm(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )
