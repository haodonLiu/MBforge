use std::path::PathBuf;

// NOTE: Keep in sync with src/mbforge/utils/constants.py (Python sidecar).
// When changing a value here, update the corresponding Python constant.

pub const APP_NAME: &str = "MBForge";
pub const APP_VERSION: &str = "0.2.0";
/// 项目元数据格式版本号。每次改变 .mbforge/ 目录结构时递增。
pub const PROJECT_FORMAT_VERSION: u32 = 1;
pub const PROJECT_META_DIR: &str = ".mbforge";

// Default models
pub const DEFAULT_EMBED_MODEL: &str = "Qwen/Qwen3-Embedding-0.6B";
pub const DEFAULT_RERANK_MODEL: &str = "Qwen/Qwen3-Reranker-0.6B";
pub const DEFAULT_LLM_MODEL: &str = "Qwen/Qwen2.5-7B-Instruct-GGUF";

// HF mirror
pub const DEFAULT_HF_ENDPOINT: &str = "https://hf-mirror.com";

// Chunking
pub const PDF_CHUNK_SIZE: usize = 512;
pub const PDF_CHUNK_OVERLAP: usize = 128;

// LLM defaults
pub const LLM_MAX_TOKENS: u32 = 4096;
pub const LLM_TEMPERATURE: f32 = 0.7;
pub const LLM_TOP_P: f32 = 0.9;

// Supported file extensions
pub const SUPPORTED_DOC_EXTS: &[&str] = &[".md", ".txt", ".pdf"];
pub const SUPPORTED_MOL_EXTS: &[&str] = &[".sdf", ".mol", ".mol2", ".pdb", ".smi"];

// Provider strings
pub const PROVIDER_OPENAI_COMPATIBLE: &str = "openai_compatible";
pub const PROVIDER_ANTHROPIC: &str = "anthropic";
pub const PROVIDER_QWEN3: &str = "qwen3";
pub const PROVIDER_SENTENCE_TRANSFORMERS: &str = "sentence_transformers";
pub const PROVIDER_OLLAMA: &str = "ollama";

// Subdirectory names
pub const MEMORY_DIR: &str = "memory";
pub const TRAJECTORY_DIR: &str = "trajectory";
pub const TRAJECTORY_FILE: &str = "trajectory.json";
pub const SUMMARY_DIR: &str = "summaries";
pub const INDEX_FILE: &str = "index.json";
pub const SETTINGS_FILE: &str = "settings.json";

// Metadata keys
pub const META_SOURCE: &str = "source";
pub const META_FILENAME: &str = "filename";
pub const META_DOC_ID: &str = "doc_id";

// Sidecar
pub const DEFAULT_SIDECAR_PORT: u16 = 18792;
pub const DEFAULT_SIDECAR_URL: &str = "http://127.0.0.1:18792";
pub const DEFAULT_EMBED_BASE_URL: &str = "http://127.0.0.1:18792";

// Agent
pub const AGENT_MAX_ITERATIONS: usize = 5;
pub const AGENT_MAX_HISTORY_ROUNDS: usize = 20;
pub const AGENT_MAX_TOTAL_TOKENS: usize = 32000;

/// Get the sidecar URL from environment variable, falling back to DEFAULT_SIDECAR_URL.
pub fn sidecar_url() -> String {
    std::env::var("MBFORGE_SIDECAR_URL")
        .unwrap_or_else(|_| DEFAULT_SIDECAR_URL.to_string())
}

/// 模型下载目录（统一入口，可通过 config.json 的 model_cache_dir 覆盖）
pub const MODEL_CACHE_DIR: &str = ".cache/mbforge/models";

/// 获取模型下载目录（优先使用 config 中的配置，否则使用默认路径）
pub fn model_cache_dir() -> PathBuf {
    let config = super::config::AppConfig::load();
    if !config.model_cache_dir.is_empty() {
        PathBuf::from(&config.model_cache_dir)
    } else {
        directories::ProjectDirs::from("", APP_NAME, APP_NAME)
            .map(|d| d.data_dir().join("models"))
            .unwrap_or_else(|| PathBuf::from(".").join(MODEL_CACHE_DIR))
    }
}

// Platform-specific config/data dirs
pub fn global_config_dir() -> PathBuf {
    directories::ProjectDirs::from("", APP_NAME, APP_NAME)
        .map(|d| d.config_dir().to_path_buf())
        .unwrap_or_else(|| PathBuf::from(".").join(".mbforge_config"))
}

pub fn global_data_dir() -> PathBuf {
    directories::ProjectDirs::from("", APP_NAME, APP_NAME)
        .map(|d| d.data_dir().to_path_buf())
        .unwrap_or_else(|| PathBuf::from(".").join(".mbforge_data"))
}
