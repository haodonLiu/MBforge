"""Embedder 模型管理（服务进程内）."""

from __future__ import annotations

from .singleton import ModelSingleton
from mbforge.models.base import BaseEmbedder
from mbforge.models.embedding import create_embedder_from_config

_mgr = ModelSingleton(BaseEmbedder, lambda cfg: cfg.embed, create_embedder_from_config)
get_embedder = _mgr.get
reset_embedder = _mgr.reset
