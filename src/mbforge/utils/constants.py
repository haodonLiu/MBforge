"""MBForge 全局常量 — 从 constants.yaml 自动生成."""

# ============================================================
# AUTO-GENERATED from constants.yaml — DO NOT EDIT MANUALLY
# Run: python scripts/generate_constants.py
# ============================================================

from __future__ import annotations

import os
from pathlib import Path

try:
    from platformdirs import user_config_dir, user_data_dir
except ImportError:
    user_config_dir = user_data_dir = lambda *a, **kw: str(Path.home() / ".config" / a[0] if a else ".config")

# NOTE: Keep in sync with src-tauri/src/core/constants.rs (Rust side).
# When changing a value here, update the corresponding Rust constant.

APP_NAME = "MBForge"
APP_VERSION = "0.2.0"
APP_AUTHOR = "MBForge"

PROJECT_FORMAT_VERSION = 2
PROJECT_META_DIR = ".mbforge"

MEMORY_DIR = "memory"
TRAJECTORY_DIR = "trajectory"
TRAJECTORY_FILE = "trajectory.json"
SUMMARY_DIR = "summaries"
INDEX_FILE = "index.json"
SETTINGS_FILE = "settings.json"
MOL_DB_FILENAME = "molecules.db"
KB_COLLECTION_DOCS = "documents"

DEFAULT_EMBED_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_RERANK_MODEL = "Qwen/Qwen3-Reranker-0.6B"
DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"

PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_QWEN3 = "qwen3"
PROVIDER_SENTENCE_TRANSFORMERS = "sentence_transformers"
PROVIDER_OLLAMA = "ollama"
PROVIDER_API = "api"
PROVIDER_LOCAL = "local"
OCR_PROVIDER_NONE = "none"

LLM_MAX_TOKENS = 4096
LLM_TEMPERATURE = 0.7
LLM_TOP_P = 0.9

PDF_CHUNK_SIZE = 512
PDF_CHUNK_OVERLAP = 128

DEFAULT_SIDECAR_PORT = 18792
DEFAULT_SIDECAR_URL = "http://127.0.0.1:18792"

SUPPORTED_DOC_EXTS: set[str] = {".md", ".txt", ".pdf"}
SUPPORTED_MOL_EXTS: set[str] = {".sdf", ".mol", ".mol2", ".pdb", ".smi"}

# ===== Python-only constants (not shared with Rust) =====

# Qwen3 Embedding/Reranker 指令前缀
EMBED_INSTRUCTION_RETRIEVAL = "Given a web search query, retrieve relevant passages that answer the query"
EMBED_INSTRUCTION_CLUSTER = "Given a document, retrieve relevant passages that are semantically similar"
RERANK_DEFAULT_INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query"

# ===== Path helpers =====

GLOBAL_CONFIG_DIR = Path(user_config_dir(APP_NAME, APP_AUTHOR))
GLOBAL_DATA_DIR = Path(user_data_dir(APP_NAME, APP_AUTHOR))


def get_model_cache_dir() -> str:
    """获取模型缓存目录（优先配置文件，其次默认路径）."""
    try:
        from .config import load_global_config
        cfg = load_global_config()
        if cfg.model_cache_dir:
            return cfg.model_cache_dir
    except Exception:
        pass
    return str(Path.home() / MODEL_CACHE_DIR.replace(".", "").replace("/", os.sep).replace("~", str(Path.home())))


# MODEL_CACHE_DIR is the relative path fragment used by get_model_cache_dir()
MODEL_CACHE_DIR = ".cache/mbforge/models"


def ensure_hf_mirror() -> None:
    """设置 HuggingFace 镜像环境变量（如果未设置）。"""
    if not os.environ.get("HF_ENDPOINT"):
        os.environ["HF_ENDPOINT"] = DEFAULT_HF_ENDPOINT

