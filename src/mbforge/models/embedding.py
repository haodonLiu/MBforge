"""Embedding 模型实现."""

from __future__ import annotations

from typing import List

import numpy as np

from .base import BaseEmbedder


class SentenceTransformerEmbedder(BaseEmbedder):
    """基于 sentence-transformers 的本地 Embedding."""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None
        self._dim = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, device=self.device)
            self._dim = self._model.get_sentence_embedding_dimension()
        return self._model

    @property
    def dim(self) -> int:
        self._load_model()
        return self._dim or 384

    def embed(self, texts: List[str]) -> List[List[float]]:
        model = self._load_model()
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return embeddings.tolist()

    async def aembed(self, texts: List[str]) -> List[List[float]]:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed, texts)


class APIEmbedder(BaseEmbedder):
    """通过 API 调用的 Embedding（OpenAI 兼容格式）."""

    def __init__(self, base_url: str, api_key: str, model_name: str = ""):
        self.client = openai.OpenAI(base_url=base_url, api_key=api_key or "empty")
        self.model_name = model_name

    def embed(self, texts: List[str]) -> List[List[float]]:
        response = self.client.embeddings.create(
            model=self.model_name,
            input=texts,
        )
        return [item.embedding for item in response.data]

    async def aembed(self, texts: List[str]) -> List[List[float]]:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed, texts)


def create_embedder_from_config(config):
    """从配置创建 Embedder 实例."""
    from ..utils.config import EmbedConfig
    cfg: EmbedConfig = config
    if cfg.provider == "sentence_transformers":
        return SentenceTransformerEmbedder(model_name=cfg.model_name, device=cfg.device)
    elif cfg.provider in ("openai", "api"):
        return APIEmbedder(base_url=cfg.base_url, api_key=cfg.api_key, model_name=cfg.model_name)
    else:
        return SentenceTransformerEmbedder(model_name=cfg.model_name, device=cfg.device)
