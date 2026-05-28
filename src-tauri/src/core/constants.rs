use std::path::PathBuf;

pub const APP_NAME: &str = "MBForge";
pub const APP_VERSION: &str = "0.2.0";
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

// Metadata keys
pub const META_SOURCE: &str = "source";
pub const META_FILENAME: &str = "filename";
pub const META_DOC_ID: &str = "doc_id";

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
