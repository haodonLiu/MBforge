"""Qwen3 backends (合并 qwen3_embed + qwen3_rerank).

两个后端都是 transformers-based，都走"从本地路径加载 + 错误捕获"流程。
合并后共享 LazyBackend 骨架，每个子模块只实现 _load_impl / inference。
"""
# ruff: noqa: E402  （import 顺序略）

from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer

from ..utils.constants import (
    DEFAULT_EMBED_MODEL,
    DEFAULT_RERANK_MODEL,
    EMBED_INSTRUCTION_RETRIEVAL,
)
from ..utils.helpers import get_default_device
from ..utils.logger import get_logger

logger = get_logger(__name__)


def _check_local_path(name: str, model_id: str) -> Path:
    """解析本地路径；不存在时抛 FileNotFoundError（被 LazyBackend.load 捕获）。

    resolve_model_path 懒加载：避免 backends/__init__.py 与本模块互相 import。
    """
    from . import resolve_model_path  # late import: 防 __init__.py 部分初始化循环
    path = Path(resolve_model_path(model_id, model_id))
    if not path.exists():
        raise FileNotFoundError(
            f"{name} 模型未找到：{path}（请放置到 ~/mbforge/models/）"
        )
    return path


# ---------------------------------------------------------------------------
# 共享骨架：load / unload / health
# ---------------------------------------------------------------------------

class LazyBackend:
    """子模块的契约：
    - 类属性 _MODEL = None
    - 实现 _load_impl(device, **kwargs) → model
    - 实现 inference 方法（embed / rerank / predict 等）
    """

    _MODEL: Any = None
    _ERROR: str = ""

    @classmethod
    def load(cls, device: str | None = None, **kwargs) -> None:
        if cls._MODEL is not None:
            return
        try:
            cls._MODEL = cls._load_impl(device=device, **kwargs)
            cls._ERROR = ""
            logger.info("%s loaded successfully", cls.__name__)
        except Exception as exc:
            cls._MODEL = None
            cls._ERROR = str(exc)
            logger.error("%s load failed: %s", cls.__name__, exc)

    @classmethod
    def unload(cls) -> None:
        cls._MODEL = None
        cls._ERROR = ""

    @classmethod
    def health(cls) -> dict[str, str]:
        if cls._MODEL is not None:
            return {"status": "ready"}
        return {"status": "error" if cls._ERROR else "loading", "error": cls._ERROR}


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

class EmbedBackend(LazyBackend):
    _DIM: int | None = None
    _DEVICE: str = get_default_device()
    _MRL_DIM: int | None = None
    _INSTRUCTION: str = EMBED_INSTRUCTION_RETRIEVAL

    @classmethod
    def _load_impl(cls, device, mrl_dim=None, instruction=None, **_):
        cls._DEVICE = device or cls._DEVICE
        cls._MRL_DIM = mrl_dim
        cls._INSTRUCTION = instruction or EMBED_INSTRUCTION_RETRIEVAL
        path = _check_local_path("Qwen3-Embedding", DEFAULT_EMBED_MODEL)
        logger.info("Loading Qwen3-Embedding: %s (device=%s)", path, cls._DEVICE)
        model = SentenceTransformer(str(path), device=cls._DEVICE, trust_remote_code=True)
        full_dim = model.get_embedding_dimension()
        cls._DIM = cls._MRL_DIM if (cls._MRL_DIM and full_dim > cls._MRL_DIM) else full_dim
        logger.info("Model loaded. Full dim=%d, output dim=%d", full_dim, cls._DIM)
        return model

    @classmethod
    def embed(cls, texts: list[str], mrl_dim: int | None = None) -> list[list[float]]:
        if cls._MODEL is None:
            cls.load()
        if cls._MODEL is None:
            err = cls._ERROR or "model failed to load (unknown reason)"
            raise RuntimeError(f"Qwen3-Embedding not available: {err}")
        prefixed = [f"{cls._INSTRUCTION}\n{t}" for t in texts]
        embeddings = cls._MODEL.encode(
            prefixed,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        target_dim = mrl_dim if mrl_dim is not None else cls._MRL_DIM
        if target_dim and embeddings.shape[1] > target_dim:
            embeddings = embeddings[:, :target_dim]
        return embeddings.tolist()


# ---------------------------------------------------------------------------
# Reranking
# ---------------------------------------------------------------------------

_PREFIX = (
    "<|im_start|>system\n"
    "Judge whether the Document meets the requirements based on the Query and the Instruct provided. "
    'Note that the answer can only be "yes" or "no".'
    "<|im_end|>\n<|im_start|>user\n"
)
_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


class RerankBackend(LazyBackend):
    _TOKENIZER: Any = None
    _DEVICE: str = get_default_device()
    _MAX_LENGTH: int = 8192
    _PREFIX_TOKENS: list[int] | None = None
    _SUFFIX_TOKENS: list[int] | None = None
    _TOKEN_TRUE_ID: int | None = None
    _TOKEN_FALSE_ID: int | None = None

    @classmethod
    def _load_impl(cls, device, max_length=8192, **_):
        cls._DEVICE = device or cls._DEVICE
        cls._MAX_LENGTH = max_length
        path = _check_local_path("Qwen3-Reranker", DEFAULT_RERANK_MODEL)
        logger.info("Loading Qwen3-Reranker: %s (device=%s)", path, cls._DEVICE)
        cls._TOKENIZER = AutoTokenizer.from_pretrained(
            path, padding_side="left", trust_remote_code=True
        )
        # device_map 避免 meta tensor → .to() 失败；torch_dtype=fp32 避免 bf16/fp32 matmul 不匹配
        device_map = cls._DEVICE if cls._DEVICE in ("cpu", "cuda", "cuda:0", "mps") else "auto"
        cls._MODEL = AutoModelForCausalLM.from_pretrained(
            path,
            trust_remote_code=True,
            # tie_word_embeddings=true 触发，ignore_mismatched_sizes 抑制 MISSING 报告
            ignore_mismatched_sizes=True,
            device_map=device_map,
            torch_dtype=torch.float32,
        )
        cls._MODEL.eval()
        cls._TOKEN_TRUE_ID = cls._TOKENIZER.convert_tokens_to_ids("yes")
        cls._TOKEN_FALSE_ID = cls._TOKENIZER.convert_tokens_to_ids("no")
        cls._PREFIX_TOKENS = cls._TOKENIZER.encode(_PREFIX, add_special_tokens=False)
        cls._SUFFIX_TOKENS = cls._TOKENIZER.encode(_SUFFIX, add_special_tokens=False)
        return cls._MODEL

    @classmethod
    def unload(cls) -> None:
        super().unload()
        cls._TOKENIZER = None
        cls._PREFIX_TOKENS = None
        cls._SUFFIX_TOKENS = None
        cls._TOKEN_TRUE_ID = None
        cls._TOKEN_FALSE_ID = None

    @classmethod
    def rerank(cls, query: str, passages: list[str]) -> list[tuple[int, float]]:
        if not passages:
            return []
        if cls._MODEL is None:
            cls.load()
        assert cls._TOKENIZER is not None
        assert cls._MODEL is not None
        assert cls._PREFIX_TOKENS is not None
        assert cls._SUFFIX_TOKENS is not None

        max_content_len = cls._MAX_LENGTH - len(cls._PREFIX_TOKENS) - len(cls._SUFFIX_TOKENS)
        pairs = [RerankBackend._format_pair(query, p) for p in passages]
        inputs = cls._TOKENIZER(
            pairs,
            padding=False,
            truncation="longest_first",
            return_attention_mask=False,
            max_length=max_content_len,
        )
        for i, ids in enumerate(inputs["input_ids"]):
            inputs["input_ids"][i] = cls._PREFIX_TOKENS + ids + cls._SUFFIX_TOKENS
        inputs = cls._TOKENIZER.pad(inputs, padding=True, return_tensors="pt", max_length=cls._MAX_LENGTH)
        for key in inputs:
            inputs[key] = inputs[key].to(cls._DEVICE)
        with torch.no_grad():
            outputs = cls._MODEL(**inputs)
            logits = outputs.logits[:, -1, :]
            false_vec = logits[:, cls._TOKEN_FALSE_ID]
            true_vec = logits[:, cls._TOKEN_TRUE_ID]
            scores = torch.stack([false_vec, true_vec], dim=1)
            scores = torch.nn.functional.log_softmax(scores, dim=1)
            scores = scores[:, 1].exp().tolist()
        indexed = [(i, float(scores[i])) for i in range(len(passages))]
        indexed.sort(key=lambda x: x[1], reverse=True)
        return indexed

    @staticmethod
    def _format_pair(query: str, doc: str) -> str:
        return (
            f"<Instruct>: Given a web search query, retrieve relevant passages that answer the query\n"
            f"<Query>: {query}\n<Document>: {doc}"
        )


# ---------------------------------------------------------------------------
# Module-level API（保持向后兼容：server.py / test endpoint 调用 qwen3_embed.*）
# ---------------------------------------------------------------------------

def load(device: str | None = None, **kwargs) -> None:
    """Prewarm 入口：依次加载两个后端。"""
    EmbedBackend.load(device=device, **kwargs)
    RerankBackend.load(device=device, **kwargs)


def unload() -> None:
    EmbedBackend.unload()
    RerankBackend.unload()


def health() -> dict[str, str]:
    if EmbedBackend._MODEL is not None:
        return EmbedBackend.health()
    return RerankBackend.health()


def embed(texts: list[str], mrl_dim: int | None = None) -> list[list[float]]:
    return EmbedBackend.embed(texts, mrl_dim=mrl_dim)


def rerank(query: str, passages: list[str]) -> list[tuple[int, float]]:
    return RerankBackend.rerank(query, passages)
