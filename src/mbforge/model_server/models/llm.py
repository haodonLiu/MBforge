"""LLM 模型管理（服务进程内）."""

from __future__ import annotations

from mbforge.models.base import BaseLLM
from mbforge.models.llm import create_llm_from_config
from mbforge.utils.config import ModelConfig

_llm_instance: BaseLLM | None = None


def get_llm(config: ModelConfig | None = None) -> BaseLLM:
    global _llm_instance
    if _llm_instance is None:
        if config is None:
            from mbforge.utils.config import load_global_config
            config = load_global_config().llm
        _llm_instance = create_llm_from_config(config)
    return _llm_instance


def reset_llm() -> None:
    global _llm_instance
    _llm_instance = None
