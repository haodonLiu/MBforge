#![allow(dead_code)]
//! Env-driven LLM client for non-agent use cases (memory / skill extraction,
//! ad-hoc completions).
//!
//! This deliberately bypasses the rig-core `MbforgeAgent` machinery — those
//! callers want a plain request/response, no tool loop, no conversation
//! memory. The config comes from `MBFORGE_LLM_*` env vars via
//! `MbforgeProviderConfig::from_app_config` (env-only, no fallback). The
//! sidecar is fully out of the LLM path (FastAPI no longer hosts
//! `/api/v1/llm/chat`).

use serde::Deserialize;

use crate::core::agent::rig_adapter::{MbforgeProviderConfig, MbforgeProviderKind};
use crate::core::http::{client_15s, client_30s};

/// One chat message in the request payload.
#[derive(Debug, Clone, serde::Serialize)]
pub struct ChatMessage {
    pub role: String,
    pub content: String,
}

/// JSON response shape we care about — only the assistant text. Both the
/// OpenAI-compatible and the Anthropic shapes collapse to `{ "text": "..." }`
/// after we extract it in the call.
#[derive(Debug, Deserialize)]
struct CompletionEnvelope {
    #[serde(default)]
    text: Option<String>,
    #[serde(default)]
    content: Option<Vec<ContentBlock>>,
}

#[derive(Debug, Deserialize)]
struct ContentBlock {
    #[serde(default)]
    text: Option<String>,
}

/// Make a single non-streaming chat completion call against the env-configured
/// LLM provider. Returns the assistant's text content.
///
/// Env resolution is strict — if `MBFORGE_LLM_*` is missing, this returns
/// `Err` and the caller logs + skips. The agent path itself never calls
/// this; only the non-critical background extractors do, so a missing env
/// shows up as a logged warning rather than a silent skip.
pub async fn chat_simple(system: &str, user: &str) -> Result<String, String> {
    let cfg = MbforgeProviderConfig::from_app_config()?;
    chat_with_timeout(&cfg, system, user, None).await
}

/// Same as `chat_simple` but with an explicit per-call timeout. Used by
/// memory extraction which can take a few seconds on long conversations.
pub async fn chat_simple_with_timeout(
    system: &str,
    user: &str,
    timeout_secs: u64,
) -> Result<String, String> {
    let cfg = MbforgeProviderConfig::from_app_config()?;
    chat_with_timeout(&cfg, system, user, Some(timeout_secs)).await
}

async fn chat_with_timeout(
    cfg: &MbforgeProviderConfig,
    system: &str,
    user: &str,
    timeout_secs: Option<u64>,
) -> Result<String, String> {
    let client = match timeout_secs {
        Some(_) => client_30s(),
        None => client_15s(),
    };

    let (url, request) = match cfg.kind {
        MbforgeProviderKind::OpenAICompatible
        | MbforgeProviderKind::DeepSeek
        | MbforgeProviderKind::Ollama => {
            let url = format!("{}/chat/completions", cfg.base_url.trim_end_matches('/'));
            let body = serde_json::json!({
                "model": cfg.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
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
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "max_tokens": 4096,
            });
            let req = client
                .post(&url)
                .header("x-api-key", &cfg.api_key)
                .header("anthropic-version", "2023-06-01")
                .header("Content-Type", "application/json")
                .json(&body);
            (url, req)
        }
    };

    let fut = request.send();
    let resp = fut
        .await
        .map_err(|e| format!("request to {url} failed: {e}"))?;
    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        return Err(format!("HTTP {status} from {url}: {body}"));
    }
    let body = resp
        .text()
        .await
        .map_err(|e| format!("read response body from {url} failed: {e}"))?;
    let env: CompletionEnvelope = serde_json::from_str(&body).map_err(|e| {
        format!(
            "parse {url} response failed: {e}; body[:300]={}",
            body.chars().take(300).collect::<String>()
        )
    })?;
    if let Some(t) = env.text {
        return Ok(t);
    }
    if let Some(blocks) = env.content {
        for b in blocks {
            if let Some(t) = b.text {
                return Ok(t);
            }
        }
    }
    Err(format!("response from {url} had no text/content"))
}

// Allow `ChatMessage` to be constructed from a `&str` for convenience.
impl ChatMessage {
    pub fn user(content: impl Into<String>) -> Self {
        Self {
            role: "user".into(),
            content: content.into(),
        }
    }
    pub fn system(content: impl Into<String>) -> Self {
        Self {
            role: "system".into(),
            content: content.into(),
        }
    }
}
