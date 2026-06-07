"""MBForge AI model interfaces.

LLM client code has been removed: the LLM is now called directly from the
Rust core via `core::agent::rig_adapter` (driven by `MBFORGE_LLM_*` env
vars). The Python sidecar no longer hosts an LLM endpoint — it serves
embed / rerank / VLM / KB / MolDet only.
"""

from .base import BaseLLM, BaseEmbedder, BaseReranker, BaseVLM, Message, StreamChunk
from .embedding import (
    SentenceTransformerEmbedder,
    APIEmbedder,
    create_embedder_from_config,
)
from .rerank import SentenceTransformerReranker, create_reranker_from_config
from .vlm import APIVLM, create_vlm_from_config

__all__ = [
    "BaseLLM",
    "BaseEmbedder",
    "BaseReranker",
    "BaseVLM",
    "Message",
    "StreamChunk",
    "SentenceTransformerEmbedder",
    "APIEmbedder",
    "SentenceTransformerReranker",
    "APIVLM",
    "create_embedder_from_config",
    "create_reranker_from_config",
    "create_vlm_from_config",
]
