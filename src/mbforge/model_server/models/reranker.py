"""Reranker 模型管理（服务进程内）."""

from __future__ import annotations

from mbforge.models.base import BaseReranker
from mbforge.models.rerank import create_reranker_from_config
from mbforge.utils.config import RerankConfig

_reranker_instance: BaseReranker | None = None


def get_reranker(config: RerankConfig | None = None) -> BaseReranker:
    global _reranker_instance
    if _reranker_instance is None:
        if config is None:
            from mbforge.utils.config import load_global_config
            config = load_global_config().rerank
        _reranker_instance = create_reranker_from_config(config)
    return _reranker_instance


def reset_reranker() -> None:
    global _reranker_instance
    _reranker_instance = None
