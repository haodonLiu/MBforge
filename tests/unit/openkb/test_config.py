from __future__ import annotations

from mbforge.openkb.config import to_litellm_config, to_litellm_model
from mbforge.utils.config import LLMConfig


def test_to_litellm_model_passthrough_prefix() -> None:
    cfg = LLMConfig(model="openai/gpt-4")
    assert to_litellm_model(cfg) == "openai/gpt-4"


def test_to_litellm_model_ollama() -> None:
    cfg = LLMConfig(model="llama3", provider="ollama")
    assert to_litellm_model(cfg) == "ollama/llama3"


def test_to_litellm_model_openai_compatible() -> None:
    cfg = LLMConfig(model="custom", provider="openai_compatible", base_url="http://localhost:8000")
    assert to_litellm_model(cfg) == "openai/custom?api_base=http://localhost:8000"


def test_to_litellm_config_includes_api_key() -> None:
    cfg = LLMConfig(model="gpt-4", api_key="secret", temperature=0.5, max_tokens=100)
    config = to_litellm_config(cfg)
    assert config["model"] == "openai/gpt-4"
    assert config["api_key"] == "secret"
    assert config["temperature"] == 0.5
