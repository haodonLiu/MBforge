"""LLM config → LiteLLM model string mapping."""

from __future__ import annotations

from typing import Any

from ..utils.config import LLMConfig
from ..utils.logger import get_logger

logger = get_logger("mbforge.openkb.config")


def to_litellm_model(cfg: LLMConfig) -> str:
    """Map LLMConfig to a LiteLLM model string.

    Supports:
    - ``provider='ollama'`` → ``ollama/{model}`` (no api_base needed; litellm reads
      OLLAMA_HOST env or defaults to http://localhost:11434)
    - ``provider='openai_compatible'`` with base_url → ``openai/{model}?api_base={url}``
    - Already-qualified LiteLLM prefix (e.g. ``anthropic/...``, ``openai/...``): passthrough
    - Plain model name: assume OpenAI
    """
    model = cfg.model

    # Already-qualified LiteLLM provider prefix → pass through
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

    # Provider-based routing
    provider = (cfg.provider or "").lower().strip()
    if provider == "ollama":
        # litellm routes ollama/{model} to local server; OLLAMA_HOST env var
        # overrides host if set.
        return f"ollama/{model}"

    # OpenAI-compatible (with custom base_url)
    if cfg.base_url:
        return f"openai/{model}?api_base={cfg.base_url}"

    # Plain model name → assume OpenAI
    return f"openai/{model}"


def to_litellm_config(cfg: LLMConfig) -> dict[str, Any]:
    """Build a full LiteLLM call config dict from LLMConfig.

    Credentials are passed explicitly so callers never need to mutate
    ``os.environ``. LiteLLM accepts both ``api_key`` and ``api_base`` as
    completion kwargs.
    """
    model_str = to_litellm_model(cfg)
    config: dict[str, Any] = {
        "model": model_str,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
    }
    if cfg.api_key:
        config["api_key"] = cfg.api_key
    if cfg.base_url:
        config["api_base"] = cfg.base_url
    return config
