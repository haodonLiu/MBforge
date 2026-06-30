"""LLM config → LiteLLM model string mapping."""

from __future__ import annotations

from typing import Any

from ..utils.config import LLMConfig
from ..utils.logger import get_logger

logger = get_logger("mbforge.openkb.config")


def to_litellm_model(cfg: LLMConfig) -> str:
    """Map LLMConfig to a LiteLLM model string.

    Supports:
    - "openai_compatible" style: returns "openai/{model}" with api_base query param
    - "ollama" style: returns "ollama/{model}"
    - Explicit LiteLLM format (e.g. "anthropic/claude-sonnet-4-6"): passthrough
    """
    model = cfg.model

    # Already a qualified LiteLLM provider prefix — pass through
    if "/" in model and model.split("/")[0] in (
        "openai",
        "anthropic",
        "ollama",
        "gemini",
        "groq",
        "bedrock",
        "azure",
        "deepseek",
        "together",
        "mistral",
    ):
        return model

    # Ollama shorthand
    if model.startswith("ollama/"):
        return model

    # OpenAI-compatible: use api_base if provided
    if cfg.base_url:
        return f"openai/{model}?api_base={cfg.base_url}"

    # Plain model name — assume OpenAI
    return f"openai/{model}"


def to_litellm_config(cfg: LLMConfig) -> dict[str, Any]:
    """Build a full LiteLLM call config dict from LLMConfig."""
    model_str = to_litellm_model(cfg)
    config: dict[str, Any] = {
        "model": model_str,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
    }
    if cfg.api_key:
        config["api_key"] = cfg.api_key
    return config
