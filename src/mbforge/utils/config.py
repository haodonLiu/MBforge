"""配置加载与管理 — sidecar 模型推理配置 (stripped).

只保留本地模型所需的 device / cache_dir 等字段。
LLM/OCR/VLM/ModelServer 已迁移到 Rust 侧。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any

from .constants import GLOBAL_CONFIG_DIR, DEFAULT_EMBED_MODEL, DEFAULT_RERANK_MODEL
from .helpers import get_default_device, load_json, save_json


@dataclass
class EmbedConfig:
    """Embedding 模型配置 (Qwen3 only)."""

    model_name: str = DEFAULT_EMBED_MODEL
    device: str = field(default_factory=get_default_device)
    mrl_dim: int | None = None
    instruction: str = ""


@dataclass
class RerankConfig:
    """Rerank 模型配置 (Qwen3 only)."""

    model_name: str = DEFAULT_RERANK_MODEL
    device: str = field(default_factory=get_default_device)
    max_length: int = 8192


@dataclass
class AppConfig:
    """全局应用配置 (sidecar 侧裁剪版)."""

    embed: EmbedConfig = field(default_factory=EmbedConfig)
    rerank: RerankConfig = field(default_factory=RerankConfig)
    model_cache_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        embed_data = {k: v for k, v in data.get("embed", {}).items() if k in EmbedConfig.__dataclass_fields__}
        rerank_data = {k: v for k, v in data.get("rerank", {}).items() if k in RerankConfig.__dataclass_fields__}
        return cls(
            embed=EmbedConfig(**embed_data),
            rerank=RerankConfig(**rerank_data),
            model_cache_dir=data.get("model_cache_dir", ""),
        )


_CONFIG_PATH = GLOBAL_CONFIG_DIR / "config.json"
_config_cache: AppConfig | None = None


def _config_from_env() -> AppConfig:
    return AppConfig(
        embed=EmbedConfig(
            model_name=os.environ.get("MBFORGE_EMBED_MODEL", DEFAULT_EMBED_MODEL),
            device=os.environ.get("MBFORGE_EMBED_DEVICE", get_default_device()),
            mrl_dim=int(os.environ.get("MBFORGE_EMBED_MRL_DIM", "0")) or None,
            instruction=os.environ.get("MBFORGE_EMBED_INSTRUCTION", ""),
        ),
        rerank=RerankConfig(
            model_name=os.environ.get("MBFORGE_RERANK_MODEL", DEFAULT_RERANK_MODEL),
            device=os.environ.get("MBFORGE_RERANK_DEVICE", get_default_device()),
            max_length=int(os.environ.get("MBFORGE_RERANK_MAX_LENGTH", "8192")),
        ),
        model_cache_dir=os.environ.get("MBFORGE_MODEL_CACHE_DIR", ""),
    )


def load_global_config() -> AppConfig:
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    if _CONFIG_PATH.exists():
        data = load_json(_CONFIG_PATH)
        if data is not None:
            try:
                _config_cache = AppConfig.from_dict(data)
                return _config_cache
            except Exception:
                pass
    _config_cache = _config_from_env()
    save_global_config(_config_cache)
    return _config_cache


def save_global_config(config: AppConfig) -> None:
    global _config_cache
    _config_cache = config
    save_json(_CONFIG_PATH, config.to_dict())
