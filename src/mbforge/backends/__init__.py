"""Fixed model backends — shared utilities."""

from __future__ import annotations

import logging
from pathlib import Path

# qwen3_embed.py + qwen3_rerank.py 已合并到 qwen3.py
# 保留旧模块名以兼容 server.py 中的 `from .backends import qwen3_embed, qwen3_rerank`
from . import qwen3 as qwen3_embed  # noqa: F401
from . import qwen3 as qwen3_rerank  # noqa: F401
from . import zvec_backend as zvec  # noqa: F401

logger = logging.getLogger("mbforge.backends")

# 模型名 → Rust RESOURCE_CATALOG id 的映射
_MODEL_NAME_TO_RESOURCE_ID = {
    "Qwen/Qwen3-Embedding": "embedding",
    "Qwen/Qwen3-Reranker": "reranker",
    "UniParser/MolDetv2": "moldet",
    "MolDetv2": "moldet",
    "moldetv2": "moldet",
    "MolScribe": "molscribe",
}


def resolve_model_path(model_name: str, cache_name: str | None = None) -> str:
    """解析模型路径 — 统一走 ResourceManager.

    Rust resource_manager.rs 是路径解析的唯一真相源。
    """
    p = Path(model_name)
    if p.is_absolute() or (p.exists() and p.is_dir()):
        return str(model_name)

    try:
        from mbforge.core.resource_manager import (
            ResourceManager,
            _read_resolved_paths,
        )
        resolved = _read_resolved_paths()
        rid = cache_name or model_name
        for prefix, mapped in _MODEL_NAME_TO_RESOURCE_ID.items():
            if prefix.lower() in rid.lower():
                path = ResourceManager.resolve_model_for_backend(mapped)
                if path is not None:
                    logger.info(f"Resolved {rid} → {path} (via ResourceManager)")
                    return str(path)
                if resolved and mapped in resolved:
                    rpath = resolved[mapped]
                    if Path(rpath).exists():
                        logger.info(f"Resolved {rid} → {rpath} (via Rust resolved_paths)")
                        return rpath
    except ImportError:
        pass

    logger.info(f"No cached path for {model_name}")
    return model_name
