"""Qwen3-Embedding backend.

模型规格:
    - Qwen/Qwen3-Embedding-0.6B: 768-dim, 32K context, 100+ 语言
    - 支持 MRL: 可输出 768/512/256/128/64 维子向量
    - 支持 Instruction Aware: 检索/聚类/分类等任务前缀
"""

from __future__ import annotations

from sentence_transformers import SentenceTransformer

from . import resolve_model_path
from ..utils.constants import DEFAULT_EMBED_MODEL, EMBED_INSTRUCTION_RETRIEVAL
from ..utils.helpers import get_default_device
from ..utils.logger import get_logger

logger = get_logger(__name__)

_MODEL: SentenceTransformer | None = None
_DIM: int | None = None
_DEVICE: str = get_default_device()
_MRL_DIM: int | None = None
_INSTRUCTION: str = EMBED_INSTRUCTION_RETRIEVAL


def load(device: str | None = None, mrl_dim: int | None = None, instruction: str | None = None) -> None:
    """Lazy-load Qwen3-Embedding model."""
    global _MODEL, _DIM, _DEVICE, _MRL_DIM, _INSTRUCTION
    if _MODEL is not None:
        return
    _DEVICE = device or _DEVICE
    _MRL_DIM = mrl_dim
    _INSTRUCTION = instruction or EMBED_INSTRUCTION_RETRIEVAL

    model_path = resolve_model_path(DEFAULT_EMBED_MODEL, DEFAULT_EMBED_MODEL)
    logger.info(f"Loading Qwen3-Embedding: {model_path} (device={_DEVICE})")
    _MODEL = SentenceTransformer(model_path, device=_DEVICE, trust_remote_code=True)
    full_dim = _MODEL.get_embedding_dimension()
    _DIM = _MRL_DIM if (_MRL_DIM and _MRL_DIM < full_dim) else full_dim
    logger.info(f"Model loaded. Full dim={full_dim}, output dim={_DIM}")


def unload() -> None:
    """Release model and GPU memory."""
    global _MODEL, _DIM
    _MODEL = None
    _DIM = None


def health() -> dict[str, str]:
    return {"status": "ready" if _MODEL is not None else "loading"}


def embed(texts: list[str]) -> list[list[float]]:
    """Sync embedding. Caller should wrap with run_in_executor if async context."""
    if _MODEL is None:
        load()
    prefixed = [f"{_INSTRUCTION}\n{t}" for t in texts]
    embeddings = _MODEL.encode(
        prefixed,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    if _MRL_DIM and _MRL_DIM < embeddings.shape[1]:
        embeddings = embeddings[:, : _MRL_DIM]
    return embeddings.tolist()
