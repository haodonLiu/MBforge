"""配置加载与管理."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Optional

from .constants import GLOBAL_CONFIG_DIR


@dataclass
class ModelConfig:
    """AI 模型配置."""

    provider: str = "openai_compatible"  # openai_compatible | local | ollama
    base_url: str = "http://localhost:8000/v1"
    api_key: str = ""
    model_name: str = "default"
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 0.9


@dataclass
class EmbedConfig:
    """Embedding 模型配置."""

    provider: str = "sentence_transformers"  # sentence_transformers | openai | api
    model_name: str = "BAAI/bge-small-zh-v1.5"
    base_url: str = ""
    api_key: str = ""
    device: str = "cpu"


@dataclass
class RerankConfig:
    """Rerank 模型配置."""

    provider: str = "sentence_transformers"
    model_name: str = "BAAI/bge-reranker-base"
    device: str = "cpu"


@dataclass
class VLMConfig:
    """VLM 模型配置."""

    provider: str = "api"
    base_url: str = ""
    api_key: str = ""
    model_name: str = ""


@dataclass
class AppConfig:
    """全局应用配置."""

    llm: ModelConfig = field(default_factory=ModelConfig)
    embed: EmbedConfig = field(default_factory=EmbedConfig)
    rerank: RerankConfig = field(default_factory=RerankConfig)
    vlm: VLMConfig = field(default_factory=VLMConfig)
    recent_projects: list[str] = field(default_factory=list)
    theme: str = "dark"
    language: str = "zh"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AppConfig:
        return cls(
            llm=ModelConfig(**data.get("llm", {})),
            embed=EmbedConfig(**data.get("embed", {})),
            rerank=RerankConfig(**data.get("rerank", {})),
            vlm=VLMConfig(**data.get("vlm", {})),
            recent_projects=data.get("recent_projects", []),
            theme=data.get("theme", "dark"),
            language=data.get("language", "zh"),
        )


_CONFIG_PATH = GLOBAL_CONFIG_DIR / "config.json"
_config_cache: Optional[AppConfig] = None


def load_global_config() -> AppConfig:
    """加载全局配置."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            _config_cache = AppConfig.from_dict(data)
            return _config_cache
        except Exception:
            pass

    _config_cache = AppConfig()
    save_global_config(_config_cache)
    return _config_cache


def save_global_config(config: AppConfig) -> None:
    """保存全局配置."""
    global _config_cache
    _config_cache = config
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)


def get_env_or_config(key: str, default: str = "") -> str:
    """优先从环境变量获取，否则返回默认值."""
    return os.environ.get(key, default)
