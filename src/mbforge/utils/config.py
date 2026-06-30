"""配置加载与管理 — OpenKB + PageIndex 配置.

LLM 配置用于 OpenKB 文档索引和查询。
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import DEFAULT_LLM_MODEL, DEFAULT_PAGEINDEX_THRESHOLD, GLOBAL_CONFIG_DIR
from .helpers import load_json, save_json


class LLMConfig(BaseModel):
    """LLM for OpenKB indexing + query (LiteLLM format)."""

    model_config = ConfigDict(extra="ignore")

    model: str = DEFAULT_LLM_MODEL
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    pageindex_threshold: int = DEFAULT_PAGEINDEX_THRESHOLD
    language: str = "en"


class AppConfig(BaseSettings):
    """全局应用配置."""

    model_config = SettingsConfigDict(
        env_prefix="MBFORGE_",
        extra="ignore",
    )

    llm: LLMConfig = Field(default_factory=LLMConfig)
    model_cache_dir: str = ""


_CONFIG_PATH = GLOBAL_CONFIG_DIR / "config.json"


def _config_from_env() -> AppConfig:
    """从环境变量构造 Pydantic AppConfig（fallback 路径）."""
    llm_data: dict[str, Any] = {"model": DEFAULT_LLM_MODEL}
    for k, env_key in [
        ("model", "MBFORGE_LLM_MODEL"),
        ("api_key", "MBFORGE_LLM_API_KEY"),
        ("base_url", "MBFORGE_LLM_BASE_URL"),
        ("language", "MBFORGE_LLM_LANGUAGE"),
    ]:
        v = os.environ.get(env_key)
        if v is not None:
            llm_data[k] = v
    if v := os.environ.get("MBFORGE_LLM_PAGEINDEX_THRESHOLD"):
        llm_data["pageindex_threshold"] = int(v)

    return AppConfig(
        llm=LLMConfig(**llm_data),
        model_cache_dir=os.environ.get("MBFORGE_MODEL_CACHE_DIR", ""),
    )


@lru_cache(maxsize=1)
def load_global_config() -> AppConfig:
    """从 JSON 加载，失败时回退到 env 变量."""
    if _CONFIG_PATH.exists():
        data = load_json(_CONFIG_PATH)
        if data is not None:
            if "embed" in data or "rerank" in data:
                import logging

                logging.getLogger("mbforge.config").info(
                    "Legacy embed/rerank config fields ignored (removed in OpenKB migration)"
                )
            try:
                return AppConfig.model_validate(data)
            except Exception:  # noqa: BLE001
                pass
    cfg = _config_from_env()
    save_global_config(cfg)
    return cfg


def save_global_config(config: AppConfig) -> None:
    """保存到 JSON 并清空 lru_cache."""
    load_global_config.cache_clear()
    save_json(_CONFIG_PATH, config.model_dump())


def reset_config_cache() -> None:
    """测试辅助：清空 lru_cache."""
    load_global_config.cache_clear()
