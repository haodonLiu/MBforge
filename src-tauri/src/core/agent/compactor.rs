//! `SidecarCompactor` — a `rig_core::memory::Compactor` impl that
//! summarizes evicted conversation turns by POSTing them to the MBForge
//! FastAPI sidecar's `/api/v1/llm/chat` endpoint.
//!
//! # Why sidecar, not rig-direct
//!
//! The rig-direct LLM is the one configured for the *current* turn
//! (the configured `cfg.base_url`). If we called it from the compactor
//! too, we would double-bill the user for every overflow (one LLM call
//! for the turn, one for the compaction summary). The sidecar has its
//! own (typically cheaper / local) model in production and the
//! precedent for this call shape is in
//! `crate::core::agent::memory::MemoryManager::extract_from_conversation`
//! (`core/agent/memory.rs:206`) — we reuse the same URL builder and
//! the same `client_30s()` factory.
//!
//! # Recursive compaction
//!
//! Rig's `Compactor::compact` is given a `carry_over: Option<&Artifact>`
//! — the previous summary, if any. Recursive compactors should fold
//! the carry-over into the new summary so context lost in earlier
//! compactions is preserved transitively. We ignore carry-over for v1
//! (we produce a fresh summary of just the evicted slice); flagged as
//! a v2 follow-up.

use rig_core::memory::{Compactor, MemoryError};
use rig_core::message::Message;
use rig_core::wasm_compat::WasmBoxedFuture;

use crate::core::http::client_30s;

/// A summarized slice of evicted conversation. `Into<rig::Message>` so
/// the composing adapter (`MbforgeManagedMemory`) can splice it at the
/// front of the loaded history.
#[derive(Clone, Debug, Default, serde::Serialize, serde::Deserialize)]
pub struct SummaryArtifact {
    pub text: String,
}

impl From<SummaryArtifact> for Message {
    fn from(s: SummaryArtifact) -> Self {
        // The compactor output is content the LLM should treat as
        // prior context. We surface it as a user-role message with a
        // marker prefix; the LLM recognizes the bracket and won't
        // mistake it for a fresh user turn.
        Message::user(format!("[Earlier conversation summary]\n{}", s.text))
    }
}

/// Compactor that delegates to the sidecar LLM. Cheap to clone
/// (`reqwest::Client` is internally `Arc`; `String` is small).
#[derive(Clone)]
pub struct SidecarCompactor {
    pub sidecar_url: String,
}

impl SidecarCompactor {
    pub fn new(sidecar_url: impl Into<String>) -> Self {
        Self {
            sidecar_url: sidecar_url.into(),
        }
    }
}

impl Compactor for SidecarCompactor {
    type Artifact = SummaryArtifact;

    fn compact<'a>(
        &'a self,
        _conversation_id: &'a str,
        evicted: &'a [Message],
        _carry_over: Option<&'a Self::Artifact>,
    ) -> WasmBoxedFuture<'a, Result<Self::Artifact, MemoryError>> {
        Box::pin(async move {
            if evicted.is_empty() {
                return Ok(SummaryArtifact {
                    text: String::new(),
                });
            }

            // Format the evicted slice as `role: content` lines.
            let mut body_lines = Vec::with_capacity(evicted.len());
            for m in evicted {
                let (role, content) = match m {
                    Message::System { content } => ("system", content.clone()),
                    Message::User { content } => {
                        let text = match content.first_ref() {
                            rig_core::message::UserContent::Text(t) => t.text.clone(),
                            _ => String::new(),
                        };
                        ("user", text)
                    }
                    Message::Assistant { content, .. } => {
                        let text = match content.first_ref() {
                            rig_core::message::AssistantContent::Text(t) => t.text.clone(),
                            _ => String::new(),
                        };
                        ("assistant", text)
                    }
                };
                let truncated = if content.chars().count() > 500 {
                    let mut s: String = content.chars().take(500).collect();
                    s.push_str("…");
                    s
                } else {
                    content
                };
                body_lines.push(format!("{role}: {truncated}"));
            }
            let conversation = body_lines.join("\n");

            let prompt = format!(
                "请将以下对话压缩为一段不超过 200 字的中文摘要，保留关键事实（人名/数字/决定/待办）。\n\
                 如果对话为空，回复\"无内容\"。\n\n\
                 对话：\n{conversation}"
            );

            let body = serde_json::json!({
                "messages": [
                    { "role": "system", "content": "你是一个对话压缩专家。" },
                    { "role": "user",   "content": prompt }
                ]
            });

            let url = format!(
                "{}/api/v1/llm/chat",
                self.sidecar_url.trim_end_matches('/')
            );
            let client = client_30s();
            let resp = client
                .post(&url)
                .header("Content-Type", "application/json")
                .json(&body)
                .send()
                .await
                .map_err(|e| MemoryError::backend(format!("sidecar POST: {e}")))?;
            let status = resp.status();
            if !status.is_success() {
                return Err(MemoryError::backend(format!(
                    "sidecar returned {status}"
                )));
            }
            let v: serde_json::Value = resp
                .json()
                .await
                .map_err(|e| MemoryError::backend(format!("sidecar JSON: {e}")))?;
            let text = v["choices"][0]["message"]["content"]
                .as_str()
                .unwrap_or("")
                .trim()
                .to_string();
            Ok(SummaryArtifact { text })
        })
    }
}

#[cfg(test)]
mod tests {
    // The compactor is exercised end-to-end by the integration test in
    // `src-tauri/tests/test_agent_chat.rs::agent_chat_context_continuity`.
    // A unit test would need a stub HTTP server; the `#[ignore]` form
    // below is the documented fallback. Run with:
    //   cargo test -p mbforge --lib core::agent::compactor -- --ignored
    use super::*;

    #[test]
    #[ignore = "needs a stub sidecar; covered by the integration test"]
    fn test_compactor_calls_sidecar() {
        // Intentionally empty: see comment above.
        let _ = SidecarCompactor::new("http://127.0.0.1:0");
    }

    #[test]
    fn test_summary_artifact_into_message() {
        let s = SummaryArtifact {
            text: "user asked about X, assistant said Y".into(),
        };
        let m: Message = s.into();
        let extracted = match m {
            Message::User { content } => match content.first_ref() {
                rig_core::message::UserContent::Text(t) => t.text.clone(),
                _ => String::new(),
            },
            _ => String::new(),
        };
        assert!(extracted.contains("[Earlier conversation summary]"));
        assert!(extracted.contains("user asked about X"));
    }
}
