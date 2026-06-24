//! LLM provider config — env-driven or config.json fallback.
//!
//! Extracted from the archived agent module. Used by:
//! - `commands/llm.rs` — settings UI read/probe
//! - `parsers/structure/post_process.rs` — LLM post-processing calls

use crate::config::settings::env_var;
use crate::error::{AppError, AppResult, ErrorCode};

/// Which LLM provider to use.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MbforgeProviderKind {
    /// OpenAI-compatible (sidecar, real OpenAI, OpenRouter, etc.)
    OpenAICompatible,
    /// Anthropic Messages API (Claude)
    Anthropic,
    /// DeepSeek (OpenAI-compatible at api.deepseek.com/v1)
    DeepSeek,
    /// Ollama 本地推理 (OpenAI-compatible at localhost:11434/v1)
    Ollama,
}

impl MbforgeProviderKind {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::OpenAICompatible => "openai_compatible",
            Self::Anthropic => "anthropic",
            Self::DeepSeek => "deepseek",
            Self::Ollama => "ollama",
        }
    }

    pub fn from_provider_str(s: &str) -> Self {
        match s {
            "anthropic" => Self::Anthropic,
            "deepseek" => Self::DeepSeek,
            "ollama" => Self::Ollama,
            _ => Self::OpenAICompatible,
        }
    }
}

#[derive(Debug, Clone, Copy)]
enum ConfigSource {
    Env,
    Config,
}

impl ConfigSource {
    fn note(self) -> &'static str {
        match self {
            Self::Env => {
                "`MBFORGE_LLM_PROVIDER` is set, so environment variables are the active source \
                 and config.json values are ignored."
            }
            Self::Config => "Values are read from config.json / Settings UI.",
        }
    }
}

/// Configuration for the LLM provider.
#[derive(Debug, Clone)]
pub struct MbforgeProviderConfig {
    pub kind: MbforgeProviderKind,
    /// Base URL. For sidecar: `http://127.0.0.1:18792/v1`. For Anthropic: leave empty
    /// (uses `api.anthropic.com`) or set a custom proxy.
    pub base_url: String,
    /// API key for the provider.
    pub api_key: String,
    /// Model identifier (e.g. "gpt-4o-mini", "claude-sonnet-4-5", "claude-opus-4-1").
    pub model: String,
    /// HTTP request timeout in seconds.
    pub timeout_secs: u64,
    /// Anthropic-specific: beta feature flags. Empty for production-stable features.
    /// Common values: "prompt-caching-2024-07-31", "extended-thinking-2025-01-01",
    /// "context-1m-2025-08-07" (for 1M context models).
    pub anthropic_betas: Vec<String>,
}

impl MbforgeProviderConfig {
    fn validate_and_build(
        kind: MbforgeProviderKind,
        base_url: String,
        api_key: String,
        model: String,
        timeout_secs: u64,
        source: ConfigSource,
    ) -> AppResult<Self> {
        let note = source.note();
        if base_url.trim().is_empty() {
            return Err(AppError::new(
                ErrorCode::SettingsLoad,
                format!(
                    "LLM base_url is not configured. {note} Set `MBFORGE_LLM_BASE_URL` in the project-root .env \
                     or in Settings > AI Models > LLM. Examples: https://api.openai.com/v1, \
                     https://openrouter.ai/api/v1, https://api.deepseek.com/v1, or a self-hosted \
                     llama.cpp server."
                ),
            ));
        }
        if api_key.trim().is_empty() {
            return Err(AppError::new(
                ErrorCode::SettingsLoad,
                format!(
                    "LLM api_key is not configured. {note} Set `MBFORGE_LLM_API_KEY` in the project-root .env \
                     or in Settings > AI Models > LLM."
                ),
            ));
        }
        if model.trim().is_empty() {
            return Err(AppError::new(
                ErrorCode::SettingsLoad,
                format!(
                    "LLM model is not configured. {note} Set `MBFORGE_LLM_MODEL` in the project-root .env \
                     or in Settings > AI Models > LLM."
                ),
            ));
        }
        Ok(Self {
            kind,
            base_url,
            api_key,
            model,
            timeout_secs,
            anthropic_betas: Vec::new(),
        })
    }

    /// Build a config from environment variables (`.env` injected at startup)
    /// with a fallback to `config.json`.
    ///
    /// Resolution order:
    /// 1. If `MBFORGE_LLM_PROVIDER` is set in the environment, use all
    ///    `MBFORGE_LLM_*` env vars.
    /// 2. Otherwise load `AppConfig` from `config.json` and use `AppConfig.llm`.
    pub fn from_app_config() -> AppResult<Self> {
        // 1. Environment variables take precedence.
        if let Some(provider) = env_var("MBFORGE_LLM_PROVIDER").filter(|s| !s.trim().is_empty()) {
            let kind = MbforgeProviderKind::from_provider_str(&provider);
            let env = |k: &str| env_var(k).filter(|s| !s.trim().is_empty());
            let base_url = env("MBFORGE_LLM_BASE_URL").unwrap_or_default();
            let api_key = env("MBFORGE_LLM_API_KEY").unwrap_or_default();
            let model = env("MBFORGE_LLM_MODEL").unwrap_or_default();
            let timeout_secs = match env("MBFORGE_LLM_REQUEST_TIMEOUT") {
                Some(v) => match v.parse::<u64>() {
                    Ok(n) => n,
                    Err(_) => {
                        log::warn!(
                            "Invalid MBFORGE_LLM_REQUEST_TIMEOUT value {:?}; falling back to 120 seconds",
                            v
                        );
                        120
                    }
                },
                None => 120,
            };
            return Self::validate_and_build(
                kind,
                base_url,
                api_key,
                model,
                timeout_secs,
                ConfigSource::Env,
            );
        }

        // 2. Fallback to config.json (Settings UI can edit these values).
        let config = super::settings::AppConfig::load();
        let llm = &config.llm;
        let kind = MbforgeProviderKind::from_provider_str(llm.provider.as_str());
        Self::validate_and_build(
            kind,
            llm.base_url.clone(),
            llm.api_key.clone(),
            llm.model_name.clone(),
            u64::from(llm.request_timeout),
            ConfigSource::Config,
        )
    }

    /// Test-only config (no real network calls).
    pub fn for_tests() -> Self {
        Self {
            kind: MbforgeProviderKind::OpenAICompatible,
            base_url: "http://127.0.0.1:0".into(),
            api_key: "test-key".into(),
            model: "test-model".into(),
            timeout_secs: 5,
            anthropic_betas: Vec::new(),
        }
    }

    /// Test config for Anthropic.
    pub fn for_tests_anthropic() -> Self {
        Self {
            kind: MbforgeProviderKind::Anthropic,
            base_url: String::new(),
            api_key: "test-anthropic-key".into(),
            model: "claude-sonnet-4-5".into(),
            timeout_secs: 5,
            anthropic_betas: vec!["extended-thinking-2025-01-01".into()],
        }
    }
}
