//! Tauri commands that surface the **env-driven** LLM config to the
//! Settings UI and run a connectivity probe against the provider's endpoint.
//!
//! The LLM has no per-session override — Settings is read-only with respect
//! to LLM. After reading the env, the frontend calls `get_llm_env_config`
//! to display the values, and `test_llm_connection` to verify the endpoint
//! is actually reachable with the configured credentials.

use std::time::{Duration, Instant};

use serde::Serialize;

use crate::core::agent::rig_adapter::{
    MbforgeProviderConfig, MbforgeProviderKind,
};

/// Status string returned to the frontend (mirrors an enum on the TS side).
///
/// `Ok`           — the probe request got a 2xx.
/// `Unreachable`  — TCP/DNS/TLS error before any HTTP response.
/// `HttpError`    — server responded with non-2xx (carries status + body excerpt).
/// `AuthError`    — 401/403 specifically.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum LlmLinkStatus {
    Ok,
    Unreachable,
    HttpError,
    AuthError,
}

/// Read-only view of the LLM env config + last probe result. Returned by
/// both `get_llm_env_config` and `test_llm_connection`.
///
/// `api_key_set` is a boolean — the actual key never leaves the Rust
/// process. The frontend only needs to know whether it's missing so it
/// can render a warning.
#[derive(Debug, Clone, Serialize)]
pub struct LlmEnvStatus {
    pub provider: String,
    pub base_url: String,
    pub api_key_set: bool,
    pub model: String,
    pub status: LlmLinkStatus,
    /// Set on `HttpError` / `AuthError` / `Unreachable` — short, frontend-safe.
    pub error: Option<String>,
    /// HTTP status code from the probe, if any.
    pub http_status: Option<u16>,
    /// Probe round-trip time in ms. `None` if the probe didn't run.
    pub latency_ms: Option<u64>,
}

impl LlmEnvStatus {
    /// Strict read: env is the source of truth. If any required var is
    /// missing, this returns the env error verbatim — the Settings UI
    /// surfaces it as a hard error, no silent "Not configured" status.
    fn from_env() -> Result<Self, String> {
        let cfg = MbforgeProviderConfig::from_app_config()?;
        Ok(Self {
            provider: cfg.kind.as_str().to_string(),
            base_url: cfg.base_url,
            api_key_set: !cfg.api_key.is_empty(),
            model: cfg.model,
            status: LlmLinkStatus::Ok, // configured — not yet probed
            error: None,
            http_status: None,
            latency_ms: None,
        })
    }
}

/// Read the current env-derived LLM config and return it for display.
/// Does **not** perform a network probe — frontend can call
/// `test_llm_connection` separately.
#[tauri::command]
pub async fn get_llm_env_config() -> Result<LlmEnvStatus, String> {
    LlmEnvStatus::from_env()
}

/// Probe the configured LLM endpoint with a minimal request and report
/// the result. This is what powers the "link status" indicator in the
/// Settings UI.
///
/// Implementation:
/// - OpenAI-compatible → `POST {base_url}/chat/completions` with a
///   single-character user message and `max_tokens: 1`. Authorisation via
///   `Authorization: Bearer <api_key>`.
/// - Anthropic → `POST {base_url}/v1/messages` with the same minimal
///   shape. Authorisation via `x-api-key: <api_key>` plus the required
///   `anthropic-version` header.
///
/// We deliberately keep the token budget at 1 so a successful test is
/// cheap. The probe only verifies reachability + auth + endpoint shape;
/// it does not exercise tool calling.
#[tauri::command]
pub async fn test_llm_connection() -> Result<LlmEnvStatus, String> {
    // Env resolution is strict — if anything is missing, the env error
    // bubbles up. The Settings UI renders it verbatim.
    let cfg = MbforgeProviderConfig::from_app_config()?;
    let mut status = LlmEnvStatus::from_env()?;

    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
    {
        Ok(c) => c,
        Err(e) => {
            status.status = LlmLinkStatus::Unreachable;
            status.error = Some(format!("failed to build HTTP client: {e}"));
            return Ok(status);
        }
    };

    let start = Instant::now();
    let (url, request) = match cfg.kind {
        MbforgeProviderKind::OpenAICompatible => {
            let url = format!(
                "{}/chat/completions",
                cfg.base_url.trim_end_matches('/')
            );
            let body = serde_json::json!({
                "model": cfg.model,
                "messages": [{"role": "user", "content": "."}],
                "max_tokens": 1,
            });
            let req = client
                .post(&url)
                .header("Authorization", format!("Bearer {}", cfg.api_key))
                .header("Content-Type", "application/json")
                .json(&body);
            (url, req)
        }
        MbforgeProviderKind::Anthropic => {
            let url = format!("{}/v1/messages", cfg.base_url.trim_end_matches('/'));
            let body = serde_json::json!({
                "model": cfg.model,
                "messages": [{"role": "user", "content": "."}],
                "max_tokens": 1,
            });
            let req = client
                .post(&url)
                .header("x-api-key", cfg.api_key)
                .header("anthropic-version", "2023-06-01")
                .header("Content-Type", "application/json")
                .json(&body);
            (url, req)
        }
    };

    let resp = match request.send().await {
        Ok(r) => r,
        Err(e) => {
            status.status = LlmLinkStatus::Unreachable;
            status.error = Some(format!("request to {url} failed: {e}"));
            status.latency_ms = Some(start.elapsed().as_millis() as u64);
            return Ok(status);
        }
    };

    let http_status = resp.status().as_u16();
    status.http_status = Some(http_status);
    status.latency_ms = Some(start.elapsed().as_millis() as u64);

    if resp.status().is_success() {
        status.status = LlmLinkStatus::Ok;
        return Ok(status);
    }

    // Pull a short error excerpt from the body for the UI.
    let body_excerpt = resp
        .text()
        .await
        .ok()
        .map(|t| t.chars().take(400).collect::<String>())
        .unwrap_or_default();
    status.status = match http_status {
        401 | 403 => LlmLinkStatus::AuthError,
        _ => LlmLinkStatus::HttpError,
    };
    status.error = Some(format!(
        "HTTP {http_status} from {url}: {body_excerpt}"
    ));
    Ok(status)
}
