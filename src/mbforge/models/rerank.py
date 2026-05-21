"""Rerank 模型实现."""

from __future__ import annotations

from typing import List

from .base import BaseReranker
from ..utils.constants import PROVIDER_SENTENCE_TRANSFORMERS, PROVIDER_QWEN3
from ..utils.logger import get_logger

logger = get_logger(__name__)


class SentenceTransformerReranker(BaseReranker):
    """基于 sentence-transformers 的 Cross-Encoder Reranker.

    兼容 BGE-Reranker 等 CrossEncoder 格式模型。
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-base", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name, device=self.device)
        return self._model

    def rerank(self, query: str, passages: List[str]) -> List[tuple[int, float]]:
        model = self._load_model()
        pairs = [[query, p] for p in passages]
        scores = model.predict(pairs, show_progress_bar=False)
        indexed = [(i, float(scores[i])) for i in range(len(passages))]
        indexed.sort(key=lambda x: x[1], reverse=True)
        return indexed


def create_reranker_from_config(config) -> BaseReranker:
    """从配置创建 Reranker 实例."""
    from ..utils.config import RerankConfig
    from .rerank_qwen3 import Qwen3Reranker

    cfg: RerankConfig = config

    if cfg.provider == PROVIDER_QWEN3:
        return Qwen3Reranker(
            model_name=cfg.model_name,
            device=cfg.device,
            max_length=cfg.max_length,
        )
    elif cfg.provider == PROVIDER_SENTENCE_TRANSFORMERS:
        return SentenceTransformerReranker(model_name=cfg.model_name, device=cfg.device)
    else:
        # fallback to Qwen3
        return Qwen3Reranker(model_name=cfg.model_name, device=cfg.device)
