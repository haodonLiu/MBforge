//! Application settings — global `config.json` model and in-memory env overrides.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::{LazyLock, Mutex};

use serde::{Deserialize, Serialize};

use super::constants::{
    embed_base_url, global_config_dir, DEFAULT_EMBED_MODEL, DEFAULT_RERANK_MODEL,
};
use crate::error::AppResult;
use crate::helpers::{load_json, save_json, LockResultExt};

/// In-memory overrides for credentials that would otherwise live in process
/// environment variables.
///
/// `OcrConfig::apply_to_env` populates this map so settings-saved API keys can
/// be read by code that currently resolves credentials via `std::env::var`
/// without using `std::env::set_var` (which is `unsafe` on some platforms and
/// prohibited by project style).
///
/// NOTE: Uses `std::sync::Mutex` because all callers are sync (Tauri commands,
/// settings load). Migration to `tokio::sync::Mutex` requires async callers
/// throughout, tracked in tech debt #2.
static ENV_OVERRIDES: LazyLock<Mutex<HashMap<String, String>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));

/// Read a process environment variable, checking in-memory overrides first.
///
/// Resolution order:
/// 1. Value previously set by `set_env_override` (typically from saved settings).
/// 2. Actual process environment variable via `std::env::var`.
pub fn env_var(key: &str) -> Option<String> {
    let overrides = ENV_OVERRIDES.lock().into_inner();
    if let Some(value) = overrides.get(key) {
        return Some(value.clone());
    }
    std::env::var(key).ok()
}

/// Set an in-memory environment override.
pub fn set_env_override(key: &str, value: &str) {
    let mut overrides = ENV_OVERRIDES.lock().into_inner();
    overrides.insert(key.to_string(), value.to_string());
}

/// Clear in-memory overrides for the given keys.
fn clear_env_overrides(keys: &[&str]) {
    let mut overrides = ENV_OVERRIDES.lock().into_inner();
    for key in keys {
        overrides.remove(*key);
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelConfig {
    pub provider: String,
    pub base_url: String,
    pub api_key: String,
    pub model_name: String,
    pub max_tokens: u32,
    pub temperature: f32,
    pub top_p: f32,
    #[serde(default = "default_request_timeout")]
    pub request_timeout: u32,
}

impl Default for ModelConfig {
    fn default() -> Self {
        Self {
            provider: "openai_compatible".into(),
            // Empty by default — we don't want a guess that silently points at
            // an endpoint the user hasn't actually configured. The MBForge
            // sidecar (FastAPI on :18792) is *not* an OpenAI-compatible
            // endpoint; only the rig OpenAI/Anthropic clients in core/agent
            // are used, and they need a real base_url (api.openai.com/v1,
            // OpenRouter, DeepSeek, a self-hosted llama.cpp server, …).
            // `from_app_config` surfaces the empty-string case as a clear
            // "configure your LLM base_url in settings.json" error.
            base_url: String::new(),
            api_key: String::new(),
            model_name: "default".into(),
            max_tokens: 4096,
            temperature: 0.7,
            top_p: 0.9,
            request_timeout: 120,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmbedConfig {
    pub provider: String,
    pub model_name: String,
    pub base_url: String,
    pub api_key: String,
    pub device: String,
    #[serde(default)]
    pub mrl_dim: Option<i32>,
    #[serde(default)]
    pub instruction: String,
}

impl EmbedConfig {
    /// 返回 Rust 侧用于创建向量表/零向量的有效维度。
    ///
    /// 优先级：
    /// 1. 显式配置的 `mrl_dim`（也是传给 sidecar 的截断维度）
    /// 2. 默认 1024（匹配 Qwen3-Embedding-0.6B 的 full dim）
    pub fn effective_dim(&self) -> usize {
        self.mrl_dim
            .filter(|d| *d > 0)
            .map(|d| d as usize)
            .unwrap_or(1024)
    }
}

impl Default for EmbedConfig {
    fn default() -> Self {
        Self {
            provider: "qwen3".into(),
            model_name: DEFAULT_EMBED_MODEL.into(),
            base_url: embed_base_url(),
            api_key: String::new(),
            device: "cpu".into(),
            mrl_dim: None,
            instruction: String::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RerankConfig {
    pub provider: String,
    pub model_name: String,
    pub device: String,
    pub max_length: u32,
}

impl Default for RerankConfig {
    fn default() -> Self {
        Self {
            provider: "qwen3".into(),
            model_name: DEFAULT_RERANK_MODEL.into(),
            device: "cpu".into(),
            max_length: 8192,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OcrConfig {
    pub provider: String,
    pub base_url: String,
    pub api_key: String,
    pub model_name: String,
    pub use_hf_mirror: bool,
    pub use_pdf_inspector: bool,
    /// Per-backend API keys. Populated from the OCR config modal so
    /// users can configure each cloud backend without setting env vars.
    /// On app load, `AppConfig::load` calls `apply_to_env` which registers
    /// these as in-memory overrides (only if those env vars are not already
    /// set, so .env / CI configs win).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mineru_api_key: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub uniparser_api_key: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub paddleocr_api_key: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub paddleocr_host: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub paddleocr_model: Option<String>,
}

impl Default for OcrConfig {
    fn default() -> Self {
        Self {
            provider: "none".into(),
            base_url: String::new(),
            api_key: String::new(),
            model_name: String::new(),
            use_hf_mirror: false,
            use_pdf_inspector: false,
            mineru_api_key: None,
            uniparser_api_key: None,
            paddleocr_api_key: None,
            paddleocr_host: None,
            paddleocr_model: None,
        }
    }
}

impl OcrConfig {
    /// Register per-backend keys/hosts as in-memory env overrides, but only
    /// when the env var is currently unset (so explicit .env or shell exports
    /// win over saved settings).
    pub fn apply_to_env(&self) {
        const KEYS: &[&str] = &[
            "MINERU_API_KEY",
            "UNIPARSER_API_KEY",
            "PADDLEOCR_API_KEY",
            "PADDLEOCR_HOST",
            "PADDLEOCR_MODEL",
        ];
        clear_env_overrides(KEYS);

        if let Some(k) = self.mineru_api_key.as_deref() {
            if !k.trim().is_empty() && std::env::var_os("MINERU_API_KEY").is_none() {
                set_env_override("MINERU_API_KEY", k);
            }
        }
        if let Some(k) = self.uniparser_api_key.as_deref() {
            if !k.trim().is_empty() && std::env::var_os("UNIPARSER_API_KEY").is_none() {
                set_env_override("UNIPARSER_API_KEY", k);
            }
        }
        if let Some(k) = self.paddleocr_api_key.as_deref() {
            if !k.trim().is_empty() && std::env::var_os("PADDLEOCR_API_KEY").is_none() {
                set_env_override("PADDLEOCR_API_KEY", k);
            }
        }
        if let Some(h) = self.paddleocr_host.as_deref() {
            if !h.trim().is_empty() && std::env::var_os("PADDLEOCR_HOST").is_none() {
                set_env_override("PADDLEOCR_HOST", h);
            }
        }
        if let Some(m) = self.paddleocr_model.as_deref() {
            if !m.trim().is_empty() && std::env::var_os("PADDLEOCR_MODEL").is_none() {
                set_env_override("PADDLEOCR_MODEL", m);
            }
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VlmConfig {
    pub provider: String,
    pub base_url: String,
    pub api_key: String,
    pub model_name: String,
}

impl Default for VlmConfig {
    fn default() -> Self {
        Self {
            provider: "none".into(),
            base_url: String::new(),
            api_key: String::new(),
            model_name: String::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelServerConfig {
    #[serde(default = "default_host")]
    pub host: String,
    #[serde(default = "default_port")]
    pub port: u16,
    #[serde(default = "default_true")]
    pub auto_start: bool,
    #[serde(default = "default_startup_timeout")]
    pub startup_timeout: u32,
    #[serde(default = "default_health_check_interval")]
    pub health_check_interval: u32,
}

fn default_host() -> String {
    "127.0.0.1".into()
}
fn default_port() -> u16 {
    super::constants::DEFAULT_SIDECAR_PORT
}
fn default_true() -> bool {
    true
}
fn default_startup_timeout() -> u32 {
    120
}
fn default_health_check_interval() -> u32 {
    5
}
fn default_request_timeout() -> u32 {
    120
}

impl Default for ModelServerConfig {
    fn default() -> Self {
        Self {
            host: "127.0.0.1".into(),
            port: super::constants::DEFAULT_SIDECAR_PORT,
            auto_start: true,
            startup_timeout: 120,
            health_check_interval: 5,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PdfParseConfig {
    /// 文本切块字符数（默认 512）
    #[serde(default = "default_chunk_size")]
    pub chunk_size: usize,
    /// 相邻块重叠字符数（默认 50）
    #[serde(default = "default_chunk_overlap")]
    pub chunk_overlap: usize,
}

impl Default for PdfParseConfig {
    fn default() -> Self {
        Self {
            chunk_size: default_chunk_size(),
            chunk_overlap: default_chunk_overlap(),
        }
    }
}

fn default_chunk_size() -> usize {
    512
}
fn default_chunk_overlap() -> usize {
    50
}
fn default_auto_moldet_on_import() -> bool {
    true
}
fn default_moldet_batch_size() -> usize {
    10
}

/// 分子检测（MolDet）配置。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MoldetConfig {
    /// 导入 PDF 后是否自动运行快速 MoldDet 扫描。
    #[serde(default = "default_auto_moldet_on_import")]
    pub auto_moldet_on_import: bool,
    /// MoldDet 每批处理的页面数。
    #[serde(default = "default_moldet_batch_size")]
    pub moldet_batch_size: usize,
}

impl Default for MoldetConfig {
    fn default() -> Self {
        Self {
            auto_moldet_on_import: default_auto_moldet_on_import(),
            moldet_batch_size: default_moldet_batch_size(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IngestConfig {
    /// 导入 PDF 后是否自动加入处理队列。默认关闭，用户可手动触发。
    #[serde(default = "default_auto_enqueue_on_import")]
    pub auto_enqueue_on_import: bool,
}

impl Default for IngestConfig {
    fn default() -> Self {
        Self {
            auto_enqueue_on_import: default_auto_enqueue_on_import(),
        }
    }
}

fn default_auto_enqueue_on_import() -> bool {
    false
}

/// Semantic cache configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SemanticCacheConfig {
    pub enabled: bool,
    pub max_size: usize,
    pub ttl_seconds: f64,
    pub disk_persist: bool,
}

impl Default for SemanticCacheConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            max_size: 1000,
            ttl_seconds: 3600.0,
            disk_persist: true,
        }
    }
}

/// Streaming search configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamingSearchConfig {
    pub enabled: bool,
    pub yield_first: usize,
}

impl Default for StreamingSearchConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            yield_first: 3,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    #[serde(default)]
    pub model_server: ModelServerConfig,
    pub llm: ModelConfig,
    pub embed: EmbedConfig,
    pub rerank: RerankConfig,
    pub ocr: OcrConfig,
    pub vlm: VlmConfig,
    #[serde(default)]
    pub recent_projects: Vec<String>,
    /// 模型下载目录，空字符串表示使用默认值
    #[serde(default)]
    pub model_cache_dir: String,
    #[serde(default)]
    pub pdf_parse: PdfParseConfig,
    #[serde(default)]
    pub moldet: MoldetConfig,
    #[serde(default)]
    pub ingest: IngestConfig,
    pub theme: String,
    pub language: String,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            model_server: ModelServerConfig::default(),
            llm: ModelConfig::default(),
            embed: EmbedConfig::default(),
            rerank: RerankConfig::default(),
            ocr: OcrConfig::default(),
            vlm: VlmConfig::default(),
            recent_projects: Vec::new(),
            model_cache_dir: String::new(),
            pdf_parse: PdfParseConfig::default(),
            moldet: MoldetConfig::default(),
            ingest: IngestConfig::default(),
            theme: "dark".into(),
            language: "zh".into(),
        }
    }
}

impl AppConfig {
    pub fn config_path() -> PathBuf {
        global_config_dir().join("config.json")
    }

    pub fn load() -> Self {
        let path = Self::config_path();
        let config: Self = match load_json(&path) {
            Some(c) => c,
            None => {
                log::warn!(
                    "Failed to load config from {}, using defaults",
                    path.display()
                );
                Self::default()
            }
        };
        // Register OCR per-backend keys as in-memory overrides so the
        // existing `is_available()` checks (MinerU / Uniparser / PaddleOCR)
        // pick them up without code changes. Env wins over saved settings.
        config.ocr.apply_to_env();
        config
    }

    pub fn save(&self) -> AppResult<()> {
        save_json(&Self::config_path(), self)
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct OptimizationConfig {
    #[serde(default)]
    pub semantic_cache: SemanticCacheConfig,
    #[serde(default)]
    pub streaming_search: StreamingSearchConfig,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = AppConfig::default();
        assert_eq!(config.theme, "dark");
        assert_eq!(config.embed.provider, "qwen3");
    }

    #[test]
    fn test_optimization_config_default() {
        let opt = OptimizationConfig::default();
        assert!(opt.semantic_cache.enabled);
        assert!(opt.streaming_search.enabled);
        assert_eq!(opt.semantic_cache.max_size, 1000);
        assert_eq!(opt.streaming_search.yield_first, 3);
    }
}
