// ============================================================
// AUTO-GENERATED from constants.yaml — DO NOT EDIT MANUALLY
// Run: python scripts/generate_constants.py
// ============================================================

// These constants are part of the cross-language public API (frontend +
// Python sidecar). Many are not referenced from this crate's bin, but
// are stable identifiers shared across components. Suppress dead_code
// to keep the auto-generated file free of noise.
#![allow(dead_code)]

use std::path::PathBuf;

use crate::config::settings::env_var;

// NOTE: Keep in sync with src/mbforge/utils/constants.py (Python sidecar).
// When changing a value here, update the corresponding Python constant.

pub const APP_NAME: &str = "MBForge";
pub const APP_VERSION: &str = "0.2.0";
pub const PROJECT_FORMAT_VERSION: u32 = 2;
pub const PROJECT_META_DIR: &str = ".mbforge";

// ============================================================
// Canonical project folder layout (strict convention)
// ============================================================
//
// Every MBForge project MUST have these 6 directories at its root:
//   projects/  — INPUT:  one isolated DocumentProject per imported PDF
//   notes/     — INPUT:  user-written .md/.txt notes
//   molecules/ — OUTPUT: pipeline extracts .sdf/.mol/.pdb/.smi here
//   index/     — OUTPUT: vector DB, FTS, semantic cache
//   reports/   — OUTPUT: generated reports and figures
//   .mbforge/  — META:   app-managed (version.json, index.json, etc.)
//
// Each DocumentProject under projects/ has the canonical layout:
//   source.pdf           — the imported PDF (immutable source)
//   cache/               — per-document cache (detections, OCR, pages)
//   molecules/           — document-local molecule outputs
//   reports/             — document-local reports and figures
//   .mbforge/index.json  — document-level metadata
//
// The global .mbforge/index.json only stores a lightweight index of
// document-projects. The scanner walks projects/*/.mbforge/index.json
// to discover DocumentProjects. Legacy projects using papers/ are
// automatically migrated on open.
// ============================================================
pub const PROJECTS_DIR: &str = "projects";
pub const PROJECT_SOURCE_FILE: &str = "source.pdf";
pub const PAPERS_DIR: &str = "papers";
pub const NOTES_DIR: &str = "notes";
pub const MOLECULES_DIR: &str = "molecules";
pub const INDEX_DIR: &str = "index";
pub const REPORTS_DIR: &str = "reports";

/// Per-folder extension whitelist.
/// - `papers/`  accepts only .pdf
/// - `notes/`   accepts .md and .txt
///
/// Files with other extensions in either folder are reported as warnings.
pub const PAPERS_EXTS: &[&str] = &["pdf"];
pub const NOTES_EXTS: &[&str] = &["md", "txt"];

// NOTE: This file was originally auto-generated from constants.yaml.
// It has since been manually extended with Rust-only constants and helpers.
// LLM/VLM defaults removed: Rust side uses openai_compatible/anthropic APIs directly.
pub const DEFAULT_EMBED_MODEL: &str = "Qwen/Qwen3-Embedding-0.6B";
pub const DEFAULT_RERANK_MODEL: &str = "Qwen/Qwen3-Reranker-0.6B";

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
pub const PROVIDER_OLLAMA: &str = "ollama";
pub const PROVIDER_API: &str = "api";
pub const PROVIDER_LOCAL: &str = "local";

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
pub const EVT_INGEST_PROGRESS: &str = "ingest-progress";
pub const EVT_INGEST_QUEUE_UPDATE: &str = "ingest-queue-update";
pub const EVT_INGEST_WORKER_HEARTBEAT: &str = "ingest-worker-heartbeat";
/// Track C: 嵌入阶段子进度（独立于整体 ingest-progress）
pub const EVT_INGEST_EMBED: &str = "ingest-embed";
pub const EVT_INGEST_LOG: &str = "ingest-log";
/// Scanned PDF detected but no OCR API key configured for the available
/// backends. Frontend shows a modal reminding the user to configure
/// MinerU/PaddleOCR/Uniparser credentials in Settings.
/// Payload: `{ backend: "mineru"|"uniparser"|"paddleocr-online"|"paddleocr-local",
///              doc_id: String, file_path: String }`
pub const EVT_OCR_API_MISSING: &str = "ocr-api-missing";

// Agent config
pub const AGENT_MAX_ITERATIONS: usize = 5;
pub const AGENT_MAX_HISTORY_ROUNDS: usize = 20;
pub const AGENT_MAX_TOTAL_TOKENS: usize = 32000;

// ===== Path helpers =====

pub fn sidecar_url() -> String {
    env_var("MBFORGE_SIDECAR_URL").unwrap_or_else(|| DEFAULT_SIDECAR_URL.to_string())
}

/// Embedding base URL — derived from sidecar_url (always sidecar + /v1)
pub fn embed_base_url() -> String {
    format!("{}/v1", sidecar_url())
}

/// 展开前导 `~` 或 `~/` 到用户主目录。其余形式（含 `~name` 指向其他用户）原样返回。
/// Windows 上 `~` 不是 shell 展开的字符，必须在代码里显式处理。
/// 如果无法获取用户主目录，返回原始路径。
fn expand_tilde(path: &str) -> PathBuf {
    let home = directories::UserDirs::new().map(|u| u.home_dir().to_path_buf());
    if let Some(rest) = path.strip_prefix("~/").or_else(|| path.strip_prefix("~\\")) {
        if let Some(home) = home {
            return home.join(rest);
        }
    } else if path == "~" {
        if let Some(home) = home {
            return home;
        }
    }
    PathBuf::from(path)
}

pub fn model_cache_dir() -> PathBuf {
    // 1. 环境变量（最高优先级）
    if let Some(dir) = env_var("MBFORGE_MODEL_CACHE_DIR") {
        return expand_tilde(&dir);
    }
    // 2. 用户配置（设置页面配置的路径）
    let config_path = global_config_dir().join("config.json");
    match std::fs::read_to_string(&config_path) {
        Ok(config) => match serde_json::from_str::<serde_json::Value>(&config) {
            Ok(val) => {
                if let Some(dir) = val.get("model_cache_dir").and_then(|v| v.as_str()) {
                    if !dir.is_empty() {
                        return expand_tilde(dir);
                    }
                }
            }
            Err(e) => {
                log::warn!("Failed to parse {}: {}", config_path.display(), e);
            }
        },
        Err(e) if e.kind() != std::io::ErrorKind::NotFound => {
            log::warn!("Failed to read {}: {}", config_path.display(), e);
        }
        _ => {}
    }
    // 3. 默认路径
    if let Some(home) = directories::UserDirs::new().map(|u| u.home_dir().to_path_buf()) {
        return home.join("mbforge").join("models");
    }
    PathBuf::from("mbforge/models")
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
