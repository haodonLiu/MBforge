"""Qwen3-Reranker backend.

基于 CausalLM 的生成式重排序器，通过 yes/no 概率判断 query-document 相关性。
模型规格:
    - Qwen/Qwen3-Reranker-0.6B: 0.6B 参数, 32K context
    - 推理: 构造 yes/no 判断 prompt, 取 yes token 的 logits 概率
"""

from __future__ import annotations

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

from . import resolve_model_path
from ..utils.constants import DEFAULT_RERANK_MODEL
from ..utils.helpers import get_default_device
from ..utils.logger import get_logger

logger = get_logger(__name__)

_MODEL: AutoModelForCausalLM | None = None
_TOKENIZER: AutoTokenizer | None = None
_DEVICE: str = get_default_device()
_MAX_LENGTH: int = 8192

_PREFIX = (
    "<|im_start|>system\n"
    "Judge whether the Document meets the requirements based on the Query and the Instruct provided. "
    'Note that the answer can only be "yes" or "no".'
    "<|im_end|>\n<|im_start|>user\n"
)
_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"

_PREFIX_TOKENS: list[int] | None = None
_SUFFIX_TOKENS: list[int] | None = None
_TOKEN_TRUE_ID: int | None = None
_TOKEN_FALSE_ID: int | None = None


def load(device: str | None = None, max_length: int = 8192) -> None:
    """Lazy-load Qwen3-Reranker model."""
    global _MODEL, _TOKENIZER, _DEVICE, _MAX_LENGTH
    global _PREFIX_TOKENS, _SUFFIX_TOKENS, _TOKEN_TRUE_ID, _TOKEN_FALSE_ID
    if _MODEL is not None:
        return
    _DEVICE = device or _DEVICE
    _MAX_LENGTH = max_length

    model_path = resolve_model_path(DEFAULT_RERANK_MODEL, DEFAULT_RERANK_MODEL)
    logger.info(f"Loading Qwen3-Reranker: {model_path} (device={_DEVICE})")
    _TOKENIZER = AutoTokenizer.from_pretrained(
        model_path, padding_side="left", trust_remote_code=True
    )
    _MODEL = AutoModelForCausalLM.from_pretrained(model_path, trust_remote_code=True)
    _MODEL.eval()
    if _DEVICE != "cpu":
        _MODEL = _MODEL.to(_DEVICE)
    _TOKEN_TRUE_ID = _TOKENIZER.convert_tokens_to_ids("yes")
    _TOKEN_FALSE_ID = _TOKENIZER.convert_tokens_to_ids("no")
    _PREFIX_TOKENS = _TOKENIZER.encode(_PREFIX, add_special_tokens=False)
    _SUFFIX_TOKENS = _TOKENIZER.encode(_SUFFIX, add_special_tokens=False)
    logger.info("Qwen3-Reranker loaded successfully")


def unload() -> None:
    """Release model and GPU memory."""
    global _MODEL, _TOKENIZER
    global _PREFIX_TOKENS, _SUFFIX_TOKENS, _TOKEN_TRUE_ID, _TOKEN_FALSE_ID
    _MODEL = None
    _TOKENIZER = None
    _PREFIX_TOKENS = None
    _SUFFIX_TOKENS = None
    _TOKEN_TRUE_ID = None
    _TOKEN_FALSE_ID = None


def health() -> dict[str, str]:
    return {"status": "ready" if _MODEL is not None else "loading"}


def rerank(query: str, passages: list[str]) -> list[tuple[int, float]]:
    """Sync rerank. Caller should wrap with run_in_executor if async context."""
    if not passages:
        return []
    if _MODEL is None:
        load()
    assert _TOKENIZER is not None
    assert _MODEL is not None
    assert _PREFIX_TOKENS is not None
    assert _SUFFIX_TOKENS is not None

    pairs = [_format_pair(query, p) for p in passages]
    max_content_len = _MAX_LENGTH - len(_PREFIX_TOKENS) - len(_SUFFIX_TOKENS)
    inputs = _TOKENIZER(
        pairs,
        padding=False,
        truncation="longest_first",
        return_attention_mask=False,
        max_length=max_content_len,
    )
    for i, ids in enumerate(inputs["input_ids"]):
        inputs["input_ids"][i] = _PREFIX_TOKENS + ids + _SUFFIX_TOKENS
    inputs = _TOKENIZER.pad(inputs, padding=True, return_tensors="pt", max_length=_MAX_LENGTH)
    for key in inputs:
        inputs[key] = inputs[key].to(_DEVICE)
    with torch.no_grad():
        outputs = _MODEL(**inputs)
        logits = outputs.logits[:, -1, :]
        false_vec = logits[:, _TOKEN_FALSE_ID]
        true_vec = logits[:, _TOKEN_TRUE_ID]
        batch_scores = torch.stack([false_vec, true_vec], dim=1)
        batch_scores = torch.nn.functional.log_softmax(batch_scores, dim=1)
        scores = batch_scores[:, 1].exp().tolist()
    indexed = [(i, float(scores[i])) for i in range(len(passages))]
    indexed.sort(key=lambda x: x[1], reverse=True)
    return indexed


def _format_pair(query: str, doc: str) -> str:
    return f"<Instruct>: Given a web search query, retrieve relevant passages that answer the query\n<Query>: {query}\n<Document>: {doc}"
