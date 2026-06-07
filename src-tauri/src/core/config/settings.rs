use serde::{Deserialize, Serialize};
use std::path::PathBuf;

use super::constants::{
    global_config_dir, embed_base_url, DEFAULT_EMBED_MODEL, DEFAULT_RERANK_MODEL,
};
use crate::core::document::semantic_cache::SemanticCacheConfig;
use crate::core::document::stream_search::StreamingSearchConfig;

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
}

impl Default for OcrConfig {
    fn default() -> Self {
        Self {
            provider: "none".into(),
            base_url: String::new(),
            api_key: String::new(),
            model_name: String::new(),
            use_hf_mirror: true,
            use_pdf_inspector: true,
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
            provider: "api".into(),
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
        crate::core::helpers::load_json(&path).unwrap_or_default()
    }

    pub fn save(&self) -> Result<(), Box<dyn std::error::Error>> {
        crate::core::helpers::save_json(&Self::config_path(), self)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OptimizationConfig {
    #[serde(default)]
    pub semantic_cache: SemanticCacheConfig,
    #[serde(default)]
    pub streaming_search: StreamingSearchConfig,
}

impl Default for OptimizationConfig {
    fn default() -> Self {
        Self {
            semantic_cache: SemanticCacheConfig::default(),
            streaming_search: StreamingSearchConfig::default(),
        }
    }
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
