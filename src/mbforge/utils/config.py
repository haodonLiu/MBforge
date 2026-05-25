"""配置加载与管理."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any

from .constants import (
    GLOBAL_CONFIG_DIR,
    PROVIDER_API,
    PROVIDER_OPENAI_COMPATIBLE,
    PROVIDER_QWEN3,
    OCR_PROVIDER_PYMUPDF,
    DEFAULT_EMBED_MODEL,
    DEFAULT_RERANK_MODEL,
)


@dataclass
class ModelConfig:
    """AI 模型配置."""

    provider: str = PROVIDER_OPENAI_COMPATIBLE  # openai_compatible | local | ollama
    base_url: str = "http://localhost:8000/v1"
    api_key: str = ""
    model_name: str = "default"
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 0.9


@dataclass
class EmbedConfig:
    """Embedding 模型配置."""

    provider: str = PROVIDER_QWEN3  # qwen3 | sentence_transformers | openai | api
    model_name: str = DEFAULT_EMBED_MODEL
    base_url: str = ""
    api_key: str = ""
    device: str = "cpu"
    mrl_dim: int | None = None  # MRL 输出维度, e.g., 256
    instruction: str = ""  # 空字符串使用默认 instruction


@dataclass
class RerankConfig:
    """Rerank 模型配置."""

    provider: str = PROVIDER_QWEN3  # qwen3 | sentence_transformers
    model_name: str = DEFAULT_RERANK_MODEL
    device: str = "cpu"
    max_length: int = 8192


@dataclass
class VLMConfig:
    """VLM 模型配置."""

    provider: str = PROVIDER_API
    base_url: str = ""
    api_key: str = ""
    model_name: str = ""


@dataclass
class OcrConfig:
    """OCR 解析配置."""

    provider: str = (
        OCR_PROVIDER_PYMUPDF  # pymupdf | glm_ocr_maas | glm_ocr_local | glm_ocr_ollama
    )
    base_url: str = ""  # 本地服务地址或 MaaS API 地址
    api_key: str = ""  # MaaS API Key
    model_name: str = ""  # 本地模型路径或 Ollama 模型名
    use_hf_mirror: bool = True  # 是否使用国内镜像下载模型


@dataclass
class AppConfig:
    """全局应用配置."""

    llm: ModelConfig = field(default_factory=ModelConfig)
    embed: EmbedConfig = field(default_factory=EmbedConfig)
    rerank: RerankConfig = field(default_factory=RerankConfig)
    vlm: VLMConfig = field(default_factory=VLMConfig)
    ocr: OcrConfig = field(default_factory=OcrConfig)
    recent_projects: list[str] = field(default_factory=list)
    theme: str = "dark"
    language: str = "zh"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        return cls(
            llm=ModelConfig(**data.get("llm", {})),
            embed=EmbedConfig(**data.get("embed", {})),
            rerank=RerankConfig(**data.get("rerank", {})),
            vlm=VLMConfig(**data.get("vlm", {})),
            ocr=OcrConfig(**data.get("ocr", {})),
            recent_projects=data.get("recent_projects", []),
            theme=data.get("theme", "dark"),
            language=data.get("language", "zh"),
        )


_CONFIG_PATH = GLOBAL_CONFIG_DIR / "config.json"
_config_cache: AppConfig | None = None


def _config_from_env() -> AppConfig:
    """从环境变量构建配置（用于 .env 文件集成）."""
    return AppConfig(
        llm=ModelConfig(
            provider=os.environ.get("MBFORGE_LLM_PROVIDER", PROVIDER_OPENAI_COMPATIBLE),
            base_url=os.environ.get("MBFORGE_LLM_BASE_URL", "http://localhost:8000/v1"),
            api_key=os.environ.get("MBFORGE_LLM_API_KEY", ""),
            model_name=os.environ.get("MBFORGE_LLM_MODEL", "default"),
            max_tokens=int(os.environ.get("MBFORGE_LLM_MAX_TOKENS", "4096")),
            temperature=float(os.environ.get("MBFORGE_LLM_TEMPERATURE", "0.7")),
            top_p=float(os.environ.get("MBFORGE_LLM_TOP_P", "0.9")),
        ),
        embed=EmbedConfig(
            provider=os.environ.get("MBFORGE_EMBED_PROVIDER", PROVIDER_QWEN3),
            model_name=os.environ.get("MBFORGE_EMBED_MODEL", DEFAULT_EMBED_MODEL),
            base_url=os.environ.get("MBFORGE_EMBED_BASE_URL", ""),
            api_key=os.environ.get("MBFORGE_EMBED_API_KEY", ""),
            device=os.environ.get("MBFORGE_EMBED_DEVICE", "cpu"),
            mrl_dim=int(os.environ.get("MBFORGE_EMBED_MRL_DIM", "0")) or None,
            instruction=os.environ.get("MBFORGE_EMBED_INSTRUCTION", ""),
        ),
        rerank=RerankConfig(
            provider=os.environ.get("MBFORGE_RERANK_PROVIDER", PROVIDER_QWEN3),
            model_name=os.environ.get("MBFORGE_RERANK_MODEL", DEFAULT_RERANK_MODEL),
            device=os.environ.get("MBFORGE_RERANK_DEVICE", "cpu"),
            max_length=int(os.environ.get("MBFORGE_RERANK_MAX_LENGTH", "8192")),
        ),
        vlm=VLMConfig(
            provider=os.environ.get("MBFORGE_VLM_PROVIDER", PROVIDER_API),
            base_url=os.environ.get("MBFORGE_VLM_BASE_URL", ""),
            api_key=os.environ.get("MBFORGE_VLM_API_KEY", ""),
            model_name=os.environ.get("MBFORGE_VLM_MODEL", ""),
        ),
        ocr=OcrConfig(
            provider=os.environ.get("MBFORGE_OCR_PROVIDER", OCR_PROVIDER_PYMUPDF),
            base_url=os.environ.get("MBFORGE_OCR_BASE_URL", ""),
            api_key=os.environ.get("MBFORGE_OCR_API_KEY", ""),
            model_name=os.environ.get("MBFORGE_OCR_MODEL", ""),
            use_hf_mirror=os.environ.get("MBFORGE_OCR_USE_HF_MIRROR", "true").lower()
            == "true",
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
        try:
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            _config_cache = AppConfig.from_dict(data)
            return _config_cache
        except Exception:
            pass

    # 尝试从环境变量读取（用于 .env 文件集成）
    _config_cache = _config_from_env()
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


def setup_hf_mirror() -> None:
    """配置 HuggingFace 国内镜像（hf-mirror）.

    在用户设置中启用 use_hf_mirror 时调用，
    使 transformers / sentence-transformers 自动从镜像站下载模型。
    """
    from .constants import DEFAULT_HF_ENDPOINT

    if "HF_ENDPOINT" not in os.environ:
        os.environ["HF_ENDPOINT"] = DEFAULT_HF_ENDPOINT
