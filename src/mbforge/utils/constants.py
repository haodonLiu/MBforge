"""MBForge 常量定义.

NOTE: Keep in sync with src-tauri/src/core/constants.rs (Rust side).
When changing a value here, update the corresponding Rust constant.
"""

from pathlib import Path
from platformdirs import user_data_dir, user_config_dir

APP_NAME = "MBForge"
APP_AUTHOR = "MBForge"
# Single source of truth for Python-side version
APP_VERSION = "0.2.0"

# 隐藏目录名，存储在项目根目录
PROJECT_META_DIR = ".mbforge"

# 全局配置目录
GLOBAL_CONFIG_DIR = Path(user_config_dir(APP_NAME, APP_AUTHOR))
GLOBAL_DATA_DIR = Path(user_data_dir(APP_NAME, APP_AUTHOR))

# 默认模型配置 — Qwen3 系列（用户选型决策）
DEFAULT_EMBED_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_RERANK_MODEL = "Qwen/Qwen3-Reranker-0.6B"
DEFAULT_LLM_MODEL = "Qwen/Qwen2.5-7B-Instruct-GGUF"
DEFAULT_VLM_MODEL = "internlm/internlm-xcomposer2-vl-7b"

# 国内模型下载镜像（ModelScope / HF-Mirror）
DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"

# Embedding 任务指令前缀（Qwen3 Instruction Aware）
EMBED_INSTRUCTION_RETRIEVAL = (
    "Given a web search query, retrieve relevant passages that answer the query"
)
EMBED_INSTRUCTION_CLUSTER = (
    "Given a document, retrieve relevant passages that are semantically similar"
)

# Reranker 默认指令（Qwen3-Reranker）
RERANK_DEFAULT_INSTRUCTION = (
    "Given a web search query, retrieve relevant passages that answer the query"
)

# 支持的文档类型
SUPPORTED_DOC_EXTS = {".md", ".txt", ".pdf"}
SUPPORTED_MOL_EXTS = {".sdf", ".mol", ".mol2", ".pdb", ".smi"}

# ChromaDB 集合名
KB_COLLECTION_DOCS = "documents"

# PDF 解析参数
PDF_CHUNK_SIZE = 512
PDF_CHUNK_OVERLAP = 128

# LLM 参数
LLM_MAX_TOKENS = 4096
LLM_TEMPERATURE = 0.7
LLM_TOP_P = 0.9

# 数据库
MOL_DB_FILENAME = "molecules.db"

# 元数据子目录/文件
MEMORY_DIR = "memory"
TRAJECTORY_DIR = "trajectory"
TRAJECTORY_FILE = "trajectory.json"
SUMMARY_DIR = "summaries"
SETTINGS_FILE = "settings.json"
INDEX_FILE = "index.json"

# Provider 字符串
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_SENTENCE_TRANSFORMERS = "sentence_transformers"
PROVIDER_QWEN3 = "qwen3"
PROVIDER_API = "api"
PROVIDER_OLLAMA = "ollama"
PROVIDER_LOCAL = "local"

# OCR Provider
OCR_PROVIDER_PYMUPDF = "pymupdf"  # Deprecated: PyMuPDF removed from project
OCR_PROVIDER_NONE = "none"

# 模型下载目录（统一入口）
def _default_model_cache_dir() -> str:
    from pathlib import Path
    return str(Path.home() / ".cache" / "mbforge" / "models")

MODEL_CACHE_DIR = _default_model_cache_dir()


def get_model_cache_dir() -> str:
    """获取有效的模型下载目录（优先使用 config 中的配置）."""
    try:
        from .config import load_global_config
        cfg = load_global_config()
        if cfg.model_cache_dir:
            return cfg.model_cache_dir
    except Exception:
        pass
    return MODEL_CACHE_DIR


def ensure_hf_mirror():
    """设置 HuggingFace 镜像环境变量（如果未设置）。"""
    import os

    if "HF_ENDPOINT" not in os.environ:
        os.environ["HF_ENDPOINT"] = DEFAULT_HF_ENDPOINT
