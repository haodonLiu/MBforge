"""Embedder 模型管理（服务进程内）."""

from __future__ import annotations

from typing import Any

from mbforge.models.embedding import create_embedder_from_config
from mbforge.utils.config import EmbedConfig

_embedder_instance: Any = None


def get_embedder(config: EmbedConfig | None = None) -> Any:
    global _embedder_instance
    if _embedder_instance is None:
        if config is None:
            from mbforge.utils.config import load_global_config
            config = load_global_config().embed
        _embedder_instance = create_embedder_from_config(config)
    return _embedder_instance


def reset_embedder() -> None:
    global _embedder_instance
    _embedder_instance = None
