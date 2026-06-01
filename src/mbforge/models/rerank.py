"""Rerank 模型实现."""

from __future__ import annotations


from .base import BaseReranker
from ..utils.config import RerankConfig
from ..utils.constants import PROVIDER_SENTENCE_TRANSFORMERS, PROVIDER_QWEN3
from ..utils.helpers import get_default_device
from ..utils.logger import get_logger

logger = get_logger(__name__)


class SentenceTransformerReranker(BaseReranker):
    """基于 sentence-transformers 的 Cross-Encoder Reranker.

    兼容 BGE-Reranker 等 CrossEncoder 格式模型。
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-base", device: str | None = None):
        self.model_name = model_name
        self.device = device or get_default_device()
        self._model = None

    def _load_model(self) -> CrossEncoder:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name, device=self.device)
        return self._model

    def rerank(self, query: str, passages: list[str]) -> list[tuple[int, float]]:
        model = self._load_model()
        pairs = [[query, p] for p in passages]
        scores = model.predict(pairs, show_progress_bar=False)
        indexed = [(i, float(scores[i])) for i in range(len(passages))]
        indexed.sort(key=lambda x: x[1], reverse=True)
        return indexed


def create_reranker_from_config(config: RerankConfig) -> BaseReranker:
    """从配置创建 Reranker 实例."""
    from .rerank_qwen3 import Qwen3Reranker

    cfg = config

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
