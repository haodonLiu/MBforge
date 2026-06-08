"""Rerank 模型实现 (Sentence-Transformers + Qwen3)."""

from __future__ import annotations

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

from .base import BaseReranker
from .embedding import _resolve_model_path
from ..utils.config import RerankConfig
from ..utils.constants import (
    DEFAULT_RERANK_MODEL,
    PROVIDER_SENTENCE_TRANSFORMERS,
    PROVIDER_QWEN3,
    ensure_hf_mirror,
)
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


class Qwen3Reranker(BaseReranker):
    """Qwen3-Reranker 重排序器.

    使用 CausalLM 的 yes/no 判断机制对候选文档进行相关性评分。
    推理流程:
        1. 为每个 (query, doc) 构造判断 prompt
        2. 取模型最后一个 token 位置 yes/no 的 logits
        3. 计算 yes 的归一化概率作为相关性分数
    """

    DEFAULT_INSTRUCTION = (
        "Given a web search query, retrieve relevant passages that answer the query"
    )

    _PREFIX = (
        "<|im_start|>system\n"
        "Judge whether the Document meets the requirements based on the Query and the Instruct provided. "
        'Note that the answer can only be "yes" or "no".'
        "<|im_end|>\n<|im_start|>user\n"
    )
    _SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"

    def __init__(
        self,
        model_name: str = DEFAULT_RERANK_MODEL,
        device: str | None = None,
        max_length: int = 8192,
        instruction: str | None = None,
    ):
        self.model_name = model_name
        self.device = device or get_default_device()
        self.max_length = max_length
        self.instruction = instruction or self.DEFAULT_INSTRUCTION
        self._tokenizer: AutoTokenizer | None = None
        self._model: AutoModelForCausalLM | None = None
        self._prefix_tokens: list[int] | None = None
        self._suffix_tokens: list[int] | None = None
        self._token_true_id: int | None = None
        self._token_false_id: int | None = None

    def _load(self) -> None:
        if self._model is not None:
            return
        ensure_hf_mirror()
        resolved = _resolve_model_path(self.model_name, self.model_name)
        logger.info(f"Loading Qwen3-Reranker model: {resolved} (device={self.device})")
        self._tokenizer = AutoTokenizer.from_pretrained(
            resolved, padding_side="left", trust_remote_code=True
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            resolved, trust_remote_code=True
        )
        self._model.eval()
        if self.device != "cpu":
            self._model = self._model.to(self.device)
        self._token_true_id = self._tokenizer.convert_tokens_to_ids("yes")
        self._token_false_id = self._tokenizer.convert_tokens_to_ids("no")
        self._prefix_tokens = self._tokenizer.encode(
            self._PREFIX, add_special_tokens=False
        )
        self._suffix_tokens = self._tokenizer.encode(
            self._SUFFIX, add_special_tokens=False
        )
        logger.info("Qwen3-Reranker model loaded successfully")

    def _format_pair(self, query: str, doc: str, instruction: str | None = None) -> str:
        inst = instruction or self.instruction
        return f"<Instruct>: {inst}\n<Query>: {query}\n<Document>: {doc}"

    def rerank(self, query: str, passages: list[str]) -> list[tuple[int, float]]:
        if not passages:
            return []
        self._load()
        assert self._tokenizer is not None
        assert self._model is not None
        assert self._prefix_tokens is not None
        assert self._suffix_tokens is not None
        pairs = [self._format_pair(query, p) for p in passages]
        max_content_len = self.max_length - len(self._prefix_tokens) - len(self._suffix_tokens)
        inputs = self._tokenizer(
            pairs,
            padding=False,
            truncation="longest_first",
            return_attention_mask=False,
            max_length=max_content_len,
        )
        for i, ids in enumerate(inputs["input_ids"]):
            inputs["input_ids"][i] = self._prefix_tokens + ids + self._suffix_tokens
        inputs = self._tokenizer.pad(
            inputs, padding=True, return_tensors="pt", max_length=self.max_length
        )
        for key in inputs:
            inputs[key] = inputs[key].to(self.device)
        with torch.no_grad():
            outputs = self._model(**inputs)
            logits = outputs.logits[:, -1, :]
            false_vec = logits[:, self._token_false_id]
            true_vec = logits[:, self._token_true_id]
            batch_scores = torch.stack([false_vec, true_vec], dim=1)
            batch_scores = torch.nn.functional.log_softmax(batch_scores, dim=1)
            scores = batch_scores[:, 1].exp().tolist()
        indexed = [(i, float(scores[i])) for i in range(len(passages))]
        indexed.sort(key=lambda x: x[1], reverse=True)
        return indexed


def create_reranker_from_config(config: RerankConfig) -> BaseReranker:
    """从配置创建 Reranker 实例."""
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


# ---- Singleton accessors (moved from model_server/models/reranker.py) ----

from ..utils.singleton import ModelSingleton

_reranker_mgr = ModelSingleton(BaseReranker, lambda cfg: cfg.rerank, create_reranker_from_config)
get_reranker = _reranker_mgr.get
reset_reranker = _reranker_mgr.reset
