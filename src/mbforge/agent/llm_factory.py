"""LLM factory — creates LangChain chat models from config.

Supports: openai, anthropic, ollama, openai_compatible.

优先级（自上而下）：
  1. 显式参数
  2. ``AppConfig.llm`` (Settings UI 写入 → ``settings.json``)
  3. 环境变量 ``MBFORGE_LLM_*`` (向后兼容 .env 用户)
  4. 硬编码默认值

Pydantic 的 ``env_prefix="MBFORGE_"`` **不会** 自动吸收 ``LLMConfig``
nested 字段的 env var（需要 ``env_nested_delimiter``，本项目未配置），
所以本模块直接保留 ``os.environ.get`` 作为 cfg 之后的兜底 —— Settings UI
的改动仍然胜出，但只设了 ``.env`` 的老用户路径不被打断。
"""

from __future__ import annotations

import os
from typing import Any

from ..utils.config import load_global_config
from ..utils.logger import get_logger

logger = get_logger("mbforge.agent.llm_factory")


def _resolve_provider(arg: str, cfg_provider: str) -> str:
    return arg or cfg_provider or "openai_compatible"


def _resolve_api_key(arg: str, cfg_key: str) -> str:
    """arg > cfg > env (cfg 优先)."""
    return arg or cfg_key or os.environ.get("MBFORGE_LLM_API_KEY", "")


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

    Priority: explicit args > AppConfig.llm > MBFORGE_LLM_* env > defaults.
    """
    llm_cfg = load_global_config().llm
    provider = _resolve_provider(provider, llm_cfg.provider)

    if provider in ("openai_compatible", "openai", "deepseek", "ollama"):
        api_key = _resolve_api_key(api_key, llm_cfg.api_key)
        if not api_key:
            raise ValueError(
                "api_key required for OpenAI-compatible provider "
                "(set via Settings UI or env MBFORGE_LLM_API_KEY)"
            )
        base_url = _resolve_base_url(base_url, llm_cfg.base_url)
        model = _resolve_model(model, llm_cfg.model, "gpt-3.5-turbo")
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
        api_key = _resolve_api_key(api_key, llm_cfg.api_key)
        if not api_key:
            raise ValueError(
                "api_key required for Anthropic provider "
                "(set via Settings UI or env MBFORGE_LLM_API_KEY)"
            )
        model = _resolve_model(model, llm_cfg.model, "claude-3-sonnet-20240229")
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
    """Create LLM from global settings (Settings UI preferred, env as fallback).

    Used by ``routers/agent.py`` lazy init. Settings UI 改动胜出,但 .env
    用户路径不被打断.
    """
    return create_llm()  # 让 create_llm 自己跑优先级链
