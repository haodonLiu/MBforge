"""Rerank 模型实现."""

from __future__ import annotations

from typing import List

from .base import BaseReranker


class SentenceTransformerReranker(BaseReranker):
    """基于 sentence-transformers 的 Cross-Encoder Reranker."""

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


def create_reranker_from_config(config):
    """从配置创建 Reranker 实例."""
    from ..utils.config import RerankConfig
    cfg: RerankConfig = config
    if cfg.provider == "sentence_transformers":
        return SentenceTransformerReranker(model_name=cfg.model_name, device=cfg.device)
    # 占位：API reranker
    return SentenceTransformerReranker(model_name=cfg.model_name, device=cfg.device)
