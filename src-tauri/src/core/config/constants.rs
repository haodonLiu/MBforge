// ============================================================
// AUTO-GENERATED from constants.yaml — DO NOT EDIT MANUALLY
// Run: python scripts/generate_constants.py
// ============================================================

use std::path::PathBuf;

// NOTE: Keep in sync with src/mbforge/utils/constants.py (Python sidecar).
// When changing a value here, update the corresponding Python constant.

pub const APP_NAME: &str = "MBForge";
pub const APP_VERSION: &str = "0.2.0";
pub const PROJECT_FORMAT_VERSION: u32 = 1;
pub const PROJECT_META_DIR: &str = ".mbforge";

// ============================================================
// Canonical project folder layout (strict convention)
// ============================================================
//
// Every MBForge project MUST have these 6 directories at its root:
//   papers/    — INPUT:  user drops .pdf files here
//   notes/     — INPUT:  user-written .md/.txt notes
//   molecules/ — OUTPUT: pipeline extracts .sdf/.mol/.pdb/.smi here
//   index/     — OUTPUT: vector DB, FTS, semantic cache
//   reports/   — OUTPUT: generated reports and figures
//   .mbforge/  — META:   app-managed (version.json, index.json, etc.)
//
// The scanner only walks papers/ and notes/. Anything placed in
// the project root directly, or in a non-canonical subfolder, is
// ignored and reported as a warning. The pipeline is the only
// writer to molecules/, index/, and reports/.
// ============================================================
pub const PAPERS_DIR: &str = "papers";
pub const NOTES_DIR: &str = "notes";
pub const MOLECULES_DIR: &str = "molecules";
pub const INDEX_DIR: &str = "index";
pub const REPORTS_DIR: &str = "reports";

/// Per-folder extension whitelist.
/// - `papers/`  accepts only .pdf
/// - `notes/`   accepts .md and .txt
/// Files with other extensions in either folder are reported as warnings.
pub const PAPERS_EXTS: &[&str] = &["pdf"];
pub const NOTES_EXTS: &[&str] = &["md", "txt"];

pub const DEFAULT_EMBED_MODEL: &str = "Qwen/Qwen3-Embedding-0.6B";
pub const DEFAULT_RERANK_MODEL: &str = "Qwen/Qwen3-Reranker-0.6B";
pub const DEFAULT_LLM_MODEL: &str = "Qwen/Qwen2.5-7B-Instruct-GGUF";
pub const DEFAULT_VLM_MODEL: &str = "mimo-v2.5";

pub const DEFAULT_HF_ENDPOINT: &str = "https://hf-mirror.com";

pub const PDF_CHUNK_SIZE: usize = 512;
pub const PDF_CHUNK_OVERLAP: usize = 128;

pub const LLM_MAX_TOKENS: u32 = 4096;
pub const LLM_TEMPERATURE: f32 = 0.7;
pub const LLM_TOP_P: f32 = 0.9;

pub const PROVIDER_OPENAI_COMPATIBLE: &str = "openai_compatible";
pub const PROVIDER_ANTHROPIC: &str = "anthropic";
pub const PROVIDER_QWEN3: &str = "qwen3";
pub const PROVIDER_SENTENCE_TRANSFORMERS: &str = "sentence_transformers";
pub const PROVIDER_API: &str = "api";

pub const MEMORY_DIR: &str = "memory";
pub const TRAJECTORY_DIR: &str = "trajectory";
pub const TRAJECTORY_FILE: &str = "trajectory.json";
pub const SUMMARY_DIR: &str = "summaries";
pub const INDEX_FILE: &str = "index.json";
pub const SETTINGS_FILE: &str = "settings.json";
pub const MOL_DB_FILENAME: &str = "molecules.db";

pub const DEFAULT_SIDECAR_PORT: u16 = 18792;
pub const DEFAULT_SIDECAR_URL: &str = "http://127.0.0.1:18792";

pub const SUPPORTED_DOC_EXTS: &[&str] = &["md", "txt", "pdf"];
pub const SUPPORTED_MOL_EXTS: &[&str] = &["sdf", "mol", "mol2", "pdb", "smi"];

// ===== Rust-only constants (not shared with Python) =====

// Metadata keys
pub const META_SOURCE: &str = "source";
pub const META_FILENAME: &str = "filename";
pub const META_DOC_ID: &str = "doc_id";

// Tauri IPC event names
pub const EVT_DOC_PROGRESS: &str = "doc-progress";
pub const EVT_DOC_RESULT: &str = "doc-result";
pub const EVT_SIDECAR_LOG: &str = "sidecar://log";
pub const EVT_SIDECAR_STATUS: &str = "sidecar://status";
pub const EVT_AGENT_STREAM_CHUNK: &str = "agent-stream-chunk";
pub const EVT_AGENT_STREAM_DONE: &str = "agent-stream-done";
pub const EVT_KB_SEARCH_CHUNK: &str = "kb-search-chunk";
pub const EVT_MODEL_DOWNLOAD_PROGRESS: &str = "model-download-progress";

// Agent config
pub const AGENT_MAX_ITERATIONS: usize = 5;
pub const AGENT_MAX_HISTORY_ROUNDS: usize = 20;
pub const AGENT_MAX_TOTAL_TOKENS: usize = 32000;

// ===== Path helpers =====

pub fn sidecar_url() -> String {
    std::env::var("MBFORGE_SIDECAR_URL").unwrap_or_else(|_| DEFAULT_SIDECAR_URL.to_string())
}

/// Embedding base URL — derived from sidecar_url (always sidecar + /v1)
pub fn embed_base_url() -> String {
    format!("{}/v1", sidecar_url())
}

pub fn model_cache_dir() -> PathBuf {
    // 1. 环境变量（最高优先级）
    if let Ok(dir) = std::env::var("MBFORGE_MODEL_CACHE_DIR") {
        return PathBuf::from(dir);
    }
    // 2. 用户配置（设置页面配置的路径）
    if let Ok(config) = std::fs::read_to_string(global_config_dir().join("config.json")) {
        if let Ok(val) = serde_json::from_str::<serde_json::Value>(&config) {
            if let Some(dir) = val.get("model_cache_dir").and_then(|v| v.as_str()) {
                if !dir.is_empty() {
                    return PathBuf::from(dir);
                }
            }
        }
    }
    // 3. 默认路径
    if let Some(home) = directories::UserDirs::new().map(|u| u.home_dir().to_path_buf()) {
        return home.join(".cache").join("mbforge").join("models");
    }
    PathBuf::from(".cache/mbforge/models")
}

pub fn global_config_dir() -> PathBuf {
    directories::ProjectDirs::from("", "", "MBForge")
        .map(|d| d.config_dir().to_path_buf())
        .unwrap_or_else(|| PathBuf::from(".").join(".config").join("MBForge"))
}

pub fn global_data_dir() -> PathBuf {
    directories::ProjectDirs::from("", "", "MBForge")
        .map(|d| d.data_dir().to_path_buf())
        .unwrap_or_else(|| {
            PathBuf::from(".")
                .join(".local")
                .join("share")
                .join("MBForge")
        })
}
