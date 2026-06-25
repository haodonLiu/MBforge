// ============================================================
// Hand-written constants for mbforge-infra.
//
// YAML-derived shared constants live in `super::generated` (auto-generated
// at build time from `constants.yaml` via `scripts/generate_constants.py`).
// They are re-exported from `super` so call sites can write
// `use crate::config::DEFAULT_SIDECAR_PORT;` unchanged.
//
// This file holds Rust-only constants and helpers that have no analogue
// on the Python side (Tauri event names, env resolution, project layout).
// ============================================================

use std::path::PathBuf;

use crate::config::settings::env_var;

// Re-export YAML-derived constants so existing call sites that write
// `config::constants::DEFAULT_SIDECAR_PORT` keep working.
#[allow(unused_imports)]
pub use super::generated::*;

// ===== Project layout (Rust-only; not in constants.yaml) =====
//
// Canonical project folder layout (strict convention):
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

// ===== Metadata keys =====
pub const META_SOURCE: &str = "source";
pub const META_FILENAME: &str = "filename";
pub const META_DOC_ID: &str = "doc_id";

// ===== Tauri IPC event names =====
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

// ===== Agent config (Rust-only tuning; not in constants.yaml) =====
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
