"""Embedding 模型实现."""

from __future__ import annotations

import os

from .base import BaseEmbedder, run_sync_async
from ..utils.config import EmbedConfig
from ..utils.constants import (
    DEFAULT_EMBED_MODEL,
    EMBED_INSTRUCTION_RETRIEVAL,
    EMBED_INSTRUCTION_CLUSTER,
    PROVIDER_SENTENCE_TRANSFORMERS,
    PROVIDER_QWEN3,
    ensure_hf_mirror,
)
from ..utils.helpers import get_default_device
from ..utils.logger import get_logger

logger = get_logger(__name__)


def _resolve_model_path(model_name: str, cache_name: str) -> str:
    """解析模型路径 — 读取 Rust 写入的 resolved_paths.json.

    Rust resource_manager.rs 是路径解析的唯一真相源。
    Rust 在启动时将解析结果写入 ~/.config/MBForge/resolved_paths.json。
    Python 直接读取，不再自己搜索缓存目录。
    """
    from pathlib import Path

    # 已经是本地路径
    p = Path(model_name)
    if p.is_absolute() or (p.exists() and p.is_dir()):
        return model_name

    # 读取 Rust 写入的路径文件
    resolved = _read_resolved_paths()
    if resolved:
        # model_name → resource_id 映射
        resource_id = _model_name_to_resource_id(cache_name)
        if resource_id and resource_id in resolved:
            path = resolved[resource_id]
            if Path(path).exists():
                logger.info(f"Resolved {cache_name} → {path} (via Rust resource_manager)")
                return path

    # 回退：返回原名（走 HuggingFace 下载）
    logger.info(f"No cached path for {model_name}, will try HuggingFace download")
    return model_name


def _model_name_to_resource_id(model_name: str) -> str | None:
    """将模型名映射到 resource_manager 的 resource_id."""
    mapping = {
        "Qwen/Qwen3-Embedding": "embedding",
        "Qwen/Qwen3-Reranker": "reranker",
        "yujieq/MolDetect": "moldet",
        "yujieq/MolScribe": "molscribe",
    }
    model_lower = model_name.lower()
    for prefix, rid in mapping.items():
        if prefix.lower() in model_lower:
            return rid
    return None


_RESOLVED_PATHS_CACHE: dict[str, str] | None = None
_RESOLVED_PATHS_MTIME: float = 0.0


def _read_resolved_paths() -> dict[str, str] | None:
    """读取 Rust 写入的 resolved_paths.json（按 mtime 失效的轻量缓存）."""
    global _RESOLVED_PATHS_CACHE, _RESOLVED_PATHS_MTIME

    from pathlib import Path
    import json

    config_dir = Path.home() / ".config" / "MBForge"
    path = config_dir / "resolved_paths.json"
    if not path.exists():
        return None

    try:
        mtime = path.stat().st_mtime
        if _RESOLVED_PATHS_CACHE is not None and mtime == _RESOLVED_PATHS_MTIME:
            return _RESOLVED_PATHS_CACHE
        with open(path) as f:
            data = json.load(f)
        _RESOLVED_PATHS_CACHE = data
        _RESOLVED_PATHS_MTIME = mtime
        logger.info(f"Loaded resolved paths from {path}: {list(data.keys())}")
        return data
    except Exception as e:
        logger.warning(f"Failed to read resolved_paths.json: {e}")
        return None


class SentenceTransformerEmbedder(BaseEmbedder):
    """基于 sentence-transformers 的本地 Embedding.

    兼容 BGE、GTE 等 sentence-transformers 格式模型。
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5", device: str | None = None):
        self.model_name = model_name
        self.device = device or get_default_device()
        self._model = None
        self._dim = None

    def _load_model(self) -> "SentenceTransformer":
        if self._model is None:
            ensure_hf_mirror()
            from sentence_transformers import SentenceTransformer

            resolved = _resolve_model_path(self.model_name, self.model_name)
            self._model = SentenceTransformer(
                resolved, device=self.device, trust_remote_code=True
            )
            self._dim = self._model.get_embedding_dimension()
        return self._model

    @property
    def dim(self) -> int:
        self._load_model()
        return self._dim or 384

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        embeddings = model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        return embeddings.tolist()

    async def aembed(self, texts: list[str]) -> list[list[float]]:
        return await run_sync_async(self.embed, texts)


class Qwen3Embedder(BaseEmbedder):
    """基于 Qwen3-Embedding 的本地 Embedding.

    支持 Instruction Aware（不同任务前缀）和 MRL（Matryoshka Representation Learning）。

    模型规格:
        - Qwen/Qwen3-Embedding-0.6B: 768-dim, 32K context, 100+ 语言
        - 支持 MRL: 可输出 768/512/256/128/64 维子向量
        - 支持 Instruction Aware: 检索/聚类/分类等任务前缀

    使用示例:
        >>> embedder = Qwen3Embedder(device="cuda")
        >>> embeddings = embedder.embed(["化合物 A 的活性如何？"])
        >>> len(embeddings[0])
        768
    """

    # 任务指令前缀（必须添加以获得最佳检索效果）
    INSTRUCTION_RETRIEVAL = EMBED_INSTRUCTION_RETRIEVAL
    INSTRUCTION_CLUSTER = EMBED_INSTRUCTION_CLUSTER
    INSTRUCTION_CLASSIFICATION = "Classify the user query."

    def __init__(
        self,
        model_name: str = DEFAULT_EMBED_MODEL,
        device: str | None = None,
        mrl_dim: int | None = None,
        instruction: str | None = None,
    ):
        self.model_name = model_name
        self.device = device or get_default_device()
        self.mrl_dim = mrl_dim  # MRL 输出维度，如 256
        self.instruction = instruction or self.INSTRUCTION_RETRIEVAL
        self._model = None
        self._dim = None

    def _load_model(self) -> "SentenceTransformer":
        if self._model is None:
            ensure_hf_mirror()
            from sentence_transformers import SentenceTransformer

            resolved = _resolve_model_path(self.model_name, self.model_name)
            logger.info(
                f"Loading Qwen3-Embedding model: {resolved} (device={self.device})"
            )
            self._model = SentenceTransformer(
                resolved,
                device=self.device,
                trust_remote_code=True,
            )
            full_dim = self._model.get_embedding_dimension()
            self._dim = (
                self.mrl_dim if (self.mrl_dim and self.mrl_dim < full_dim) else full_dim
            )
            logger.info(f"Model loaded. Full dim={full_dim}, output dim={self._dim}")
        return self._model

    @property
    def dim(self) -> int:
        self._load_model()
        return self._dim or 768

    def embed(self, texts: list[str]) -> list[list[float]]:
        """编码文本，自动添加 instruction 前缀."""
        model = self._load_model()
        # 为每个文本添加 instruction 前缀
        prefixed = [f"{self.instruction}\n{t}" for t in texts]
        embeddings = model.encode(
            prefixed,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        # MRL: 截取指定维度
        if self.mrl_dim and self.mrl_dim < embeddings.shape[1]:
            embeddings = embeddings[:, : self.mrl_dim]
        return embeddings.tolist()

    async def aembed(self, texts: list[str]) -> list[list[float]]:
        return await run_sync_async(self.embed, texts)


class APIEmbedder(BaseEmbedder):
    """通过 API 调用的 Embedding（OpenAI 兼容格式）."""

    def __init__(self, base_url: str, api_key: str, model_name: str = ""):
        import openai

        self.client = openai.OpenAI(base_url=base_url, api_key=api_key or "empty")
        self.model_name = model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.model_name,
            input=texts,
        )
        return [item.embedding for item in response.data]

    async def aembed(self, texts: list[str]) -> list[list[float]]:
        return await run_sync_async(self.embed, texts)


def create_embedder_from_config(config: EmbedConfig) -> BaseEmbedder:
    """从配置创建 Embedder 实例."""
    from ..utils.constants import PROVIDER_API

    cfg: EmbedConfig = config

    if cfg.provider == PROVIDER_QWEN3:
        mrl = cfg.mrl_dim if cfg.mrl_dim else None
        return Qwen3Embedder(
            model_name=cfg.model_name,
            device=cfg.device,
            mrl_dim=mrl,
            instruction=cfg.instruction or None,
        )
    elif cfg.provider == PROVIDER_SENTENCE_TRANSFORMERS:
        return SentenceTransformerEmbedder(model_name=cfg.model_name, device=cfg.device)
    elif cfg.provider in ("openai", PROVIDER_API):
        return APIEmbedder(
            base_url=cfg.base_url, api_key=cfg.api_key, model_name=cfg.model_name
        )
    else:
        # fallback to Qwen3
        return Qwen3Embedder(model_name=cfg.model_name, device=cfg.device)


# ---- Singleton accessors (moved from model_server/models/embedder.py) ----

from ..utils.singleton import ModelSingleton

_embedder_mgr = ModelSingleton(BaseEmbedder, lambda cfg: cfg.embed, create_embedder_from_config)
get_embedder = _embedder_mgr.get
reset_embedder = _embedder_mgr.reset
