"""Reranker 模型管理（服务进程内）."""

from __future__ import annotations

from .singleton import ModelSingleton
from mbforge.models.base import BaseReranker
from mbforge.models.rerank import create_reranker_from_config

_mgr = ModelSingleton(BaseReranker, lambda cfg: cfg.rerank, create_reranker_from_config)
get_reranker = _mgr.get
reset_reranker = _mgr.reset
