"""Qwen3 backends (合并 qwen3_embed + qwen3_rerank).

两个后端都是 transformers-based，都走"从本地路径加载 + 错误捕获"流程。
合并后共享 LazyBackend 骨架，每个子模块只实现 _load_impl / inference。

Embedding 走 Provider 抽象层（Phase 2）：支持本地 SentenceTransformer
和外部 OpenAI 兼容 API（如阿里云百炼 / OpenAI / OpenRouter / DeepSeek），
通过 EmbedConfig.provider 切换。
"""
# ruff: noqa: E402  （import 顺序略）

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import torch
from openai import OpenAI
from sentence_transformers import SentenceTransformer
from transformers import AutoModel, AutoTokenizer

from ..utils.config import load_global_config
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
# Embedding Provider 抽象层
# ---------------------------------------------------------------------------


class EmbeddingProvider(ABC):
    """Embedding 后端抽象接口。

    实现类：
    - LocalSentenceTransformerProvider：本地 SentenceTransformer + PyTorch
    - OpenAICompatibleProvider：外部 OpenAI 兼容 API（百炼 / OpenAI / OpenRouter / DeepSeek）

    设计要点：
    - 统一接口（embed / health）让 EmbedBackend 不知道具体后端
    - load() / unload() 负责资源生命周期
    - 返回 list[list[float]] 与原 SentenceTransformer 行为一致（numpy → list）
    """

    @abstractmethod
    def load(self) -> None: ...

    @abstractmethod
    def embed(
        self, texts: list[str], mrl_dim: int | None = None
    ) -> list[list[float]]: ...

    @abstractmethod
    def unload(self) -> None: ...

    @abstractmethod
    def health(self) -> dict[str, str]: ...

    @abstractmethod
    def dim(self) -> int: ...


class LocalSentenceTransformerProvider(EmbeddingProvider):
    """本地 SentenceTransformer + PyTorch（默认 provider）。"""

    def __init__(
        self,
        model_name: str,
        device: str,
        instruction: str,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._instruction = instruction
        self._model: SentenceTransformer | None = None
        self._full_dim: int = 0
        self._error: str = ""

    def load(self) -> None:
        path = _check_local_path("Qwen3-Embedding", self._model_name)
        logger.info(
            "Loading Qwen3-Embedding (local): %s (device=%s)", path, self._device
        )
        self._model = SentenceTransformer(
            str(path), device=self._device, trust_remote_code=True
        )
        self._full_dim = self._model.get_embedding_dimension()

    def embed(self, texts: list[str], mrl_dim: int | None = None) -> list[list[float]]:
        if self._model is None:
            raise RuntimeError(f"Local embedder not available: {self._error}")
        prefixed = [f"{self._instruction}\n{t}" for t in texts]
        embeddings = self._model.encode(
            prefixed,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        target = mrl_dim if mrl_dim is not None else None
        if target and embeddings.shape[1] > target:
            embeddings = embeddings[:, :target]
        return embeddings.tolist()

    def unload(self) -> None:
        self._model = None
        self._error = ""

    def health(self) -> dict[str, str]:
        if self._model is not None:
            return {"status": "ready"}
        return {"status": "error" if self._error else "loading", "error": self._error}

    def dim(self) -> int:
        return self._full_dim


class OpenAICompatibleProvider(EmbeddingProvider):
    """外部 OpenAI 兼容 Embedding API（阿里云百炼 / OpenAI / OpenRouter / DeepSeek）。

    调用路径：POST {base_url}/embeddings（OpenAI 兼容）
    Auth：Authorization: Bearer {api_key}
    Body: {"model": ..., "input": [...]}
    Response: {"data": [{"embedding": [...]}, ...], "usage": {...}}
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._client: OpenAI | None = None
        self._dim: int = 0
        self._error: str = ""

    def load(self) -> None:
        if not self._api_key:
            raise ValueError(
                f"provider=openai_compatible but api_key is empty; set {self._model}'s api_key in Settings"
            )
        if not self._base_url:
            raise ValueError(
                f"provider=openai_compatible but base_url is empty; configure {self._model}'s base_url in Settings"
            )
        logger.info(
            "Loading Embedding (openai_compatible): model=%s base_url=%s",
            self._model,
            self._base_url,
        )
        # OpenAI 客户端创建很轻（懒连接）；首次 embed 才发请求
        self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        # 探测维度：发 1 个最小请求取 response.data[0].embedding 长度
        try:
            resp = self._client.embeddings.create(
                model=self._model, input=["health probe"]
            )
            self._dim = len(resp.data[0].embedding)
        except Exception as exc:
            raise RuntimeError(
                f"Embedding probe failed: model={self._model} base_url={self._base_url}: {exc}"
            ) from exc

    def embed(self, texts: list[str], mrl_dim: int | None = None) -> list[list[float]]:
        if self._client is None:
            raise RuntimeError(
                f"openai_compatible embedder not available: {self._error}"
            )
        if not texts:
            return []
        # OpenAI 兼容接口支持 str 或 list[str]；batch 整批传更高效
        resp = self._client.embeddings.create(
            model=self._model,
            input=texts,
        )
        # resp.data 按 index 排序；保险起见显式 sort
        vectors = [item.embedding for item in sorted(resp.data, key=lambda d: d.index)]
        # MRL 维度截断（与本地 provider 行为一致）
        if mrl_dim and len(vectors[0]) > mrl_dim:
            vectors = [v[:mrl_dim] for v in vectors]
        return vectors

    def unload(self) -> None:
        self._client = None
        self._error = ""

    def health(self) -> dict[str, str]:
        if self._client is not None:
            return {"status": "ready"}
        return {"status": "error" if self._error else "loading", "error": self._error}

    def dim(self) -> int:
        return self._dim


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


def _build_embed_provider() -> EmbeddingProvider:
    """根据 EmbedConfig 构造对应的 provider。

    选择规则：
    1. provider == "openai_compatible" 且 api_key 非空 → OpenAICompatibleProvider
    2. 否则（默认）→ LocalSentenceTransformerProvider

    配置读取来源（按优先级）：
    1. load_global_config().embed（用户从 settings UI 设置的）
    2. 环境变量 MBFORGE_EMBED_*（fallback）
    """
    cfg = load_global_config().embed
    provider_name = (cfg.provider or "qwen3").lower()
    api_key = cfg.api_key or os.environ.get("MBFORGE_EMBED_API_KEY", "")
    base_url = cfg.base_url or os.environ.get("MBFORGE_EMBED_BASE_URL", "")

    if provider_name == "openai_compatible" and api_key:
        return OpenAICompatibleProvider(
            base_url=base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=api_key,
            model=cfg.model_name or "text-embedding-v4",
        )

    # 默认：本地 SentenceTransformer
    return LocalSentenceTransformerProvider(
        model_name=cfg.model_name or DEFAULT_EMBED_MODEL,
        device=cfg.device or get_default_device(),
        instruction=cfg.instruction or EMBED_INSTRUCTION_RETRIEVAL,
    )


class EmbedBackend(LazyBackend):
    _PROVIDER: EmbeddingProvider | None = None
    _DIM: int | None = None
    _MRL_DIM: int | None = None

    @classmethod
    def _load_impl(cls, provider=None, mrl_dim=None, **_):
        """加载 embedding 后端。

        参数 provider 是 EmbeddingProvider 实例（用于测试时注入 mock），
        生产路径从 _build_embed_provider() 读取。
        """
        cls._PROVIDER = provider or _build_embed_provider()
        cls._PROVIDER.load()
        cls._DIM = cls._PROVIDER.dim()
        cls._MRL_DIM = mrl_dim
        full_dim = cls._DIM or 0
        if mrl_dim and full_dim > mrl_dim:
            full_dim = mrl_dim
        logger.info("Embedding loaded. effective dim=%d", full_dim)
        return cls._PROVIDER

    @classmethod
    def embed(cls, texts: list[str], mrl_dim: int | None = None) -> list[list[float]]:
        if cls._PROVIDER is None:
            cls.load()
        if cls._PROVIDER is None:
            err = cls._ERROR or "model failed to load (unknown reason)"
            raise RuntimeError(f"Embedding not available: {err}")
        target_dim = mrl_dim if mrl_dim is not None else cls._MRL_DIM
        return cls._PROVIDER.embed(texts, mrl_dim=target_dim)

    @classmethod
    def unload(cls) -> None:
        if cls._PROVIDER is not None:
            cls._PROVIDER.unload()
        cls._PROVIDER = None
        cls._DIM = None
        cls._MRL_DIM = None
        cls._ERROR = ""

    @classmethod
    def health(cls) -> dict[str, str]:
        if cls._PROVIDER is not None:
            return cls._PROVIDER.health()
        return {"status": "error" if cls._ERROR else "loading", "error": cls._ERROR}


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
    # 缓存 embed_tokens.weight 用于手动取 yes/no token 的 logits。
    # 用 AutoModel（无 head）替代 AutoModelForCausalLM：
    #   - 避免 tie_word_embeddings=true 触发 "lm_head.weight MISSING" 警告
    #   - 节省 ~600MB 显存（vocab_size × hidden × 4 bytes 未使用权重）
    _EMBED_WEIGHT: torch.Tensor | None = None

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
        device_map = (
            cls._DEVICE
            if cls._DEVICE in ("cpu", "cuda", "cuda:0", "cuda:1", "mps")
            else "auto"
        )
        cls._MODEL = AutoModel.from_pretrained(
            path,
            trust_remote_code=True,
            device_map=device_map,
            torch_dtype=torch.float32,
        )
        cls._MODEL.eval()
        # 缓存 token embedding 当作手动 lm_head（tie_word_embeddings=true 时两者权重相同）
        cls._EMBED_WEIGHT = cls._MODEL.get_input_embeddings().weight
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
        cls._EMBED_WEIGHT = None

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

        max_content_len = (
            cls._MAX_LENGTH - len(cls._PREFIX_TOKENS) - len(cls._SUFFIX_TOKENS)
        )
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
        inputs = cls._TOKENIZER.pad(
            inputs, padding=True, return_tensors="pt", max_length=cls._MAX_LENGTH
        )
        for key in inputs:
            inputs[key] = inputs[key].to(cls._DEVICE)
        with torch.no_grad():
            outputs = cls._MODEL(**inputs)
            # 手动构造 lm_head：last_hidden_state @ embed_tokens.T
            # tie_word_embeddings=true 时两者权重相同，结果与原 AutoModelForCausalLM 一致
            hidden = outputs.last_hidden_state[:, -1, :]
            logits = hidden @ cls._EMBED_WEIGHT.T  # [batch, vocab]
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
    if EmbedBackend._PROVIDER is not None:
        return EmbedBackend.health()
    return RerankBackend.health()


def embed(texts: list[str], mrl_dim: int | None = None) -> list[list[float]]:
    return EmbedBackend.embed(texts, mrl_dim=mrl_dim)


def rerank(query: str, passages: list[str]) -> list[tuple[int, float]]:
    return RerankBackend.rerank(query, passages)
