"""LLM 模型管理（服务进程内）."""

from __future__ import annotations

from .singleton import ModelSingleton
from mbforge.models.base import BaseLLM
from mbforge.models.llm import create_llm_from_config

_mgr = ModelSingleton(BaseLLM, lambda cfg: cfg.llm, create_llm_from_config)
get_llm = _mgr.get
reset_llm = _mgr.reset
