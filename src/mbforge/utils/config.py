"""配置加载与管理 — sidecar 模型推理配置.

本模块仅管理 sidecar 内部使用的配置（embed/rerank/vlm）。
LLM/OCR/ModelServer 已迁移到 Rust 侧（见 `src-tauri/src/core/config/settings.rs`），
使用 `MBFORGE_LLM_*` / `MBFORGE_OCR_*` 环境变量直驱动。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any

from .constants import (
    GLOBAL_CONFIG_DIR,
    PROVIDER_API,
    PROVIDER_QWEN3,
    DEFAULT_EMBED_MODEL,
    DEFAULT_RERANK_MODEL,
)
from .helpers import get_default_device, load_json, save_json


@dataclass
class EmbedConfig:
    """Embedding 模型配置."""

    provider: str = PROVIDER_QWEN3  # qwen3 | sentence_transformers | openai | api
    model_name: str = DEFAULT_EMBED_MODEL
    base_url: str = ""
    api_key: str = ""
    device: str = field(default_factory=get_default_device)
    mrl_dim: int | None = None  # MRL 输出维度, e.g., 256
    instruction: str = ""  # 空字符串使用默认 instruction


@dataclass
class RerankConfig:
    """Rerank 模型配置."""

    provider: str = PROVIDER_QWEN3  # qwen3 | sentence_transformers
    model_name: str = DEFAULT_RERANK_MODEL
    device: str = field(default_factory=get_default_device)
    max_length: int = 8192


@dataclass
class VLMConfig:
    """VLM 模型配置."""

    provider: str = PROVIDER_API
    base_url: str = ""
    api_key: str = ""
    model_name: str = ""


@dataclass
class AppConfig:
    """全局应用配置 (sidecar 侧裁剪版)."""

    embed: EmbedConfig = field(default_factory=EmbedConfig)
    rerank: RerankConfig = field(default_factory=RerankConfig)
    vlm: VLMConfig = field(default_factory=VLMConfig)
    recent_projects: list[str] = field(default_factory=list)
    model_cache_dir: str = ""  # 空字符串表示使用默认值 (~/.cache/mbforge/models/)
    theme: str = "dark"
    language: str = "zh"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        # 兼容旧配置文件：忽略已迁移的 llm/ocr/model_server 字段
        embed_data = {k: v for k, v in data.get("embed", {}).items() if k in EmbedConfig.__dataclass_fields__}
        rerank_data = {k: v for k, v in data.get("rerank", {}).items() if k in RerankConfig.__dataclass_fields__}
        vlm_data = {k: v for k, v in data.get("vlm", {}).items() if k in VLMConfig.__dataclass_fields__}
        return cls(
            embed=EmbedConfig(**embed_data),
            rerank=RerankConfig(**rerank_data),
            vlm=VLMConfig(**vlm_data),
            recent_projects=data.get("recent_projects", []),
            model_cache_dir=data.get("model_cache_dir", ""),
            theme=data.get("theme", "dark"),
            language=data.get("language", "zh"),
        )


_CONFIG_PATH = GLOBAL_CONFIG_DIR / "config.json"
_config_cache: AppConfig | None = None


def _config_from_env() -> AppConfig:
    """从环境变量构建配置（用于 .env 文件集成）.

    注意：LLM/OCR/ModelServer 配置不再加载——它们已迁移到 Rust 侧。
    """
    return AppConfig(
        embed=EmbedConfig(
            provider=os.environ.get("MBFORGE_EMBED_PROVIDER", PROVIDER_QWEN3),
            model_name=os.environ.get("MBFORGE_EMBED_MODEL", DEFAULT_EMBED_MODEL),
            base_url=os.environ.get("MBFORGE_EMBED_BASE_URL", ""),
            api_key=os.environ.get("MBFORGE_EMBED_API_KEY", ""),
            device=os.environ.get("MBFORGE_EMBED_DEVICE", get_default_device()),
            mrl_dim=int(os.environ.get("MBFORGE_EMBED_MRL_DIM", "0")) or None,
            instruction=os.environ.get("MBFORGE_EMBED_INSTRUCTION", ""),
        ),
        rerank=RerankConfig(
            provider=os.environ.get("MBFORGE_RERANK_PROVIDER", PROVIDER_QWEN3),
            model_name=os.environ.get("MBFORGE_RERANK_MODEL", DEFAULT_RERANK_MODEL),
            device=os.environ.get("MBFORGE_RERANK_DEVICE", get_default_device()),
            max_length=int(os.environ.get("MBFORGE_RERANK_MAX_LENGTH", "8192")),
        ),
        vlm=VLMConfig(
            provider=os.environ.get("MBFORGE_VLM_PROVIDER", PROVIDER_API),
            base_url=os.environ.get("MBFORGE_VLM_BASE_URL", ""),
            api_key=os.environ.get("MBFORGE_VLM_API_KEY", ""),
            model_name=os.environ.get("MBFORGE_VLM_MODEL", ""),
        ),
    )


def load_global_config() -> AppConfig:
    """加载全局配置.

    优先级：
    1. 内存缓存
    2. 配置文件 (~/.config/MBForge/config.json)
    3. 环境变量（支持 .env 文件）
    4. 默认值
    """
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
                # 旧配置文件可能含 llm/ocr/model_server 字段，已被 from_dict 静默忽略
                pass

    # 尝试从环境变量读取（用于 .env 文件集成）
    _config_cache = _config_from_env()
    save_global_config(_config_cache)
    return _config_cache


def save_global_config(config: AppConfig) -> None:
    """保存全局配置."""
    global _config_cache
    _config_cache = config
    save_json(_CONFIG_PATH, config.to_dict())
