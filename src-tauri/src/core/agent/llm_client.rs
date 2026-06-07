//! Env-driven LLM client for non-agent use cases (memory / skill extraction,
//! ad-hoc completions).
//!
//! This deliberately bypasses the rig-core `MbforgeAgent` machinery — those
//! callers want a plain request/response, no tool loop, no conversation
//! memory. The config still comes from `MBFORGE_LLM_*` env vars via
//! `MbforgeProviderConfig::peek_from_env`, keeping the sidecar fully out
//! of the LLM path (FastAPI no longer hosts `/api/v1/llm/chat`).

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
/// On any error (env not set / network / non-2xx), returns `None` so the
/// caller can degrade gracefully — memory / skill extraction should never
/// block the main agent flow.
pub async fn chat_simple(system: &str, user: &str) -> Option<String> {
    let cfg = MbforgeProviderConfig::peek_from_env();
    if cfg.base_url.trim().is_empty() || cfg.api_key.trim().is_empty() {
        return None;
    }
    chat_with_timeout(&cfg, system, user, None).await
}

/// Same as `chat_simple` but with an explicit per-call timeout. Used by
/// memory extraction which can take a few seconds on long conversations.
pub async fn chat_simple_with_timeout(
    system: &str,
    user: &str,
    timeout_secs: u64,
) -> Option<String> {
    let cfg = MbforgeProviderConfig::peek_from_env();
    if cfg.base_url.trim().is_empty() || cfg.api_key.trim().is_empty() {
        return None;
    }
    chat_with_timeout(&cfg, system, user, Some(timeout_secs)).await
}

async fn chat_with_timeout(
    cfg: &MbforgeProviderConfig,
    system: &str,
    user: &str,
    timeout_secs: Option<u64>,
) -> Option<String> {
    let client = match timeout_secs {
        Some(_) => client_30s(),
        None => client_15s(),
    };

    let (url, request) = match cfg.kind {
        MbforgeProviderKind::OpenAICompatible => {
            let url = format!(
                "{}/chat/completions",
                cfg.base_url.trim_end_matches('/')
            );
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
    let resp = match fut.await {
        Ok(r) => r,
        Err(e) => {
            log::warn!("llm_client: request to {url} failed: {e}");
            return None;
        }
    };
    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        log::warn!("llm_client: HTTP {status} from {url}: {body}");
        return None;
    }
    let body = resp.text().await.ok()?;
    let env: CompletionEnvelope = match serde_json::from_str(&body) {
        Ok(v) => v,
        Err(e) => {
            log::warn!("llm_client: parse {url} response failed: {e}; body[:300]={}", &body.chars().take(300).collect::<String>());
            return None;
        }
    };
    if let Some(t) = env.text {
        return Some(t);
    }
    if let Some(blocks) = env.content {
        for b in blocks {
            if let Some(t) = b.text {
                return Some(t);
            }
        }
    }
    log::warn!("llm_client: response from {url} had no text/content");
    None
}

// Allow `ChatMessage` to be constructed from a `&str` for convenience.
impl ChatMessage {
    pub fn user(content: impl Into<String>) -> Self {
        Self { role: "user".into(), content: content.into() }
    }
    pub fn system(content: impl Into<String>) -> Self {
        Self { role: "system".into(), content: content.into() }
    }
}
