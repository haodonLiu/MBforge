"""配置加载与管理 — sidecar 模型推理配置 (stripped).

只保留本地模型所需的 device / cache_dir 等字段。
LLM/OCR/VLM/ModelServer 已迁移到 Rust 侧。

Pydantic 化（v2 BaseSettings）：显式声明 Rust 端 `EmbedConfig` / `RerankConfig`
的所有字段（`provider` / `base_url` / `api_key`），保证 `model_dump()` 不会抹掉
Rust 写入的字段。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import GLOBAL_CONFIG_DIR, DEFAULT_EMBED_MODEL, DEFAULT_RERANK_MODEL
from .helpers import get_default_device, load_json, save_json


class EmbedConfig(BaseModel):
    """Embedding 模型配置 (Qwen3).

    字段必须与 Rust 端 `EmbedConfig`（`src-tauri/src/core/config/settings.rs:47`）
    完全对齐。`provider` / `base_url` / `api_key` 由 Rust 端写入，Python 端
    业务上不读，但必须保留以防 `model_dump()` 抹掉。
    """

    model_config = ConfigDict(extra="ignore")

    model_name: str = DEFAULT_EMBED_MODEL
    device: str = Field(default_factory=get_default_device)
    mrl_dim: int | None = None
    instruction: str = ""
    # Rust 端专属字段 — 显式声明保证 round-trip 兼容
    provider: str = "qwen3"
    base_url: str = ""
    api_key: str = ""


class RerankConfig(BaseModel):
    """Rerank 模型配置 (Qwen3)."""

    model_config = ConfigDict(extra="ignore")

    model_name: str = DEFAULT_RERANK_MODEL
    device: str = Field(default_factory=get_default_device)
    max_length: int = 8192
    # Rust 端专属字段
    provider: str = "qwen3"


class AppConfig(BaseSettings):
    """全局应用配置 (sidecar 侧裁剪版)."""

    model_config = SettingsConfigDict(
        # 不开 `env_nested_delimiter` — 保持 `MBFORGE_EMBED_MODEL` 单下划线兼容
        env_prefix="MBFORGE_",
        extra="ignore",
    )

    embed: EmbedConfig = Field(default_factory=EmbedConfig)
    rerank: RerankConfig = Field(default_factory=RerankConfig)
    model_cache_dir: str = ""


_CONFIG_PATH = GLOBAL_CONFIG_DIR / "config.json"


def _config_from_env() -> AppConfig:
    """从环境变量构造 Pydantic AppConfig（仅用于 fallback 路径）."""
    embed_data: dict[str, Any] = {"model_name": DEFAULT_EMBED_MODEL}
    for k, env_key in [
        ("model_name", "MBFORGE_EMBED_MODEL"),
        ("device", "MBFORGE_EMBED_DEVICE"),
        ("instruction", "MBFORGE_EMBED_INSTRUCTION"),
    ]:
        v = os.environ.get(env_key)
        if v is not None:
            embed_data[k] = v
    mrl = os.environ.get("MBFORGE_EMBED_MRL_DIM")
    if mrl:
        embed_data["mrl_dim"] = int(mrl) or None

    rerank_data: dict[str, Any] = {"model_name": DEFAULT_RERANK_MODEL}
    if v := os.environ.get("MBFORGE_RERANK_MODEL"):
        rerank_data["model_name"] = v
    if v := os.environ.get("MBFORGE_RERANK_DEVICE"):
        rerank_data["device"] = v
    if v := os.environ.get("MBFORGE_RERANK_MAX_LENGTH"):
        rerank_data["max_length"] = int(v)

    return AppConfig(
        embed=EmbedConfig(**embed_data),
        rerank=RerankConfig(**rerank_data),
        model_cache_dir=os.environ.get("MBFORGE_MODEL_CACHE_DIR", ""),
    )


@lru_cache(maxsize=1)
def load_global_config() -> AppConfig:
    """从 JSON 加载，失败时回退到 env 变量."""
    if _CONFIG_PATH.exists():
        data = load_json(_CONFIG_PATH)
        if data is not None:
            try:
                return AppConfig.model_validate(data)
            except Exception:  # noqa: BLE001 — corrupt config must fall back to env, never crash startup. See load_json above.
                pass
    cfg = _config_from_env()
    save_global_config(cfg)
    return cfg


def save_global_config(config: AppConfig) -> None:
    """保存到 JSON 并清空 lru_cache（强制下次 load 重新读文件）."""
    load_global_config.cache_clear()
    save_json(_CONFIG_PATH, config.model_dump())


def reset_config_cache() -> None:
    """测试辅助：清空 lru_cache."""
    load_global_config.cache_clear()
