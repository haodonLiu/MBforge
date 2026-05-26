"""Embedding 模型实现."""

from __future__ import annotations

import os

from .base import BaseEmbedder
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
    """解析模型路径，优先从 ModelScope 缓存加载.

    1. 如果是绝对/相对路径，直接使用
    2. 如果 ModelScope 缓存中存在，使用缓存路径
    3. 否则返回原 model_name（走 HuggingFace 下载）
    """
    from pathlib import Path

    # 已经是本地路径
    p = Path(model_name)
    if p.is_absolute() or (p.exists() and p.is_dir()):
        return model_name

    # ModelScope 缓存常见路径
    possible_cache_bases = [
        os.environ.get("MODELSCOPE_CACHE", ""),
        str(Path.home() / "Models" / "ModelScope"),
        str(Path.home() / ".cache" / "modelscope"),
    ]

    cache_base = ""
    for cb in possible_cache_bases:
        if cb and Path(cb).exists():
            cache_base = cb
            break

    if cache_base:
        # ModelScope 目录结构: <cache>/<org>/<model>-<version>
        # ModelScope 用 ___ 代替版本号的点号，如 Qwen3-Embedding-0___6B
        # 原始名如 Qwen/Qwen3-Embedding-0.6B
        # 提取关键部分用于匹配: Qwen3-Embedding-0
        name_parts = cache_name.replace("/", " ").split()
        last_part = (
            name_parts[-1] if name_parts else cache_name
        )  # e.g. Qwen3-Embedding-0.6B
        key_name = last_part.rsplit(".", 1)[0]  # e.g. Qwen3-Embedding-0

        cache_path = Path(cache_base)
        if cache_path.exists():
            for item in cache_path.rglob("*"):
                if item.is_dir() and key_name.lower() in item.name.lower():
                    logger.info(f"Found model in ModelScope cache: {item}")
                    return str(item)

    return model_name


class SentenceTransformerEmbedder(BaseEmbedder):
    """基于 sentence-transformers 的本地 Embedding.

    兼容 BGE、GTE 等 sentence-transformers 格式模型。
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5", device: str | None = None):
        self.model_name = model_name
        self.device = device or get_default_device()
        self._model = None
        self._dim = None

    def _load_model(self):
        if self._model is None:
            ensure_hf_mirror()
            from sentence_transformers import SentenceTransformer

            resolved = _resolve_model_path(self.model_name, self.model_name)
            self._model = SentenceTransformer(
                resolved, device=self.device, trust_remote_code=True
            )
            self._dim = self._model.get_sentence_embedding_dimension()
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
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.embed, texts)


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

    def _load_model(self):
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
            full_dim = self._model.get_sentence_embedding_dimension()
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
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.embed, texts)


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
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.embed, texts)


def create_embedder_from_config(config) -> BaseEmbedder:
    """从配置创建 Embedder 实例."""
    from ..utils.config import EmbedConfig
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
