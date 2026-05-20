"""MBForge 常量定义."""

from pathlib import Path
from platformdirs import user_data_dir, user_config_dir

APP_NAME = "MBForge"
APP_AUTHOR = "MBForge"
APP_VERSION = "0.1.0"

# 隐藏目录名，存储在项目根目录
PROJECT_META_DIR = ".mbforge"

# 全局配置目录
GLOBAL_CONFIG_DIR = Path(user_config_dir(APP_NAME, APP_AUTHOR))
GLOBAL_DATA_DIR = Path(user_data_dir(APP_NAME, APP_AUTHOR))

# 默认模型配置
DEFAULT_EMBED_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-base"
DEFAULT_LLM_MODEL = "Qwen/Qwen2.5-7B-Instruct-GGUF"
DEFAULT_VLM_MODEL = "internlm/internlm-xcomposer2-vl-7b"

# 支持的文档类型
SUPPORTED_DOC_EXTS = {".md", ".txt", ".pdf", ".json", ".yaml", ".yml"}
SUPPORTED_MOL_EXTS = {".sdf", ".mol", ".mol2", ".pdb", ".smi", ".csv"}

# ChromaDB 集合名
KB_COLLECTION_DOCS = "documents"
KB_COLLECTION_MOLECULES = "molecules"

# PDF 解析参数
PDF_CHUNK_SIZE = 512
PDF_CHUNK_OVERLAP = 128

# LLM 参数
LLM_MAX_TOKENS = 4096
LLM_TEMPERATURE = 0.7
LLM_TOP_P = 0.9

# 数据库
MOL_DB_FILENAME = "molecules.db"
