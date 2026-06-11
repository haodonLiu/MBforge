#![allow(dead_code)]
//! `RigDirectCompactor` — a `rig_core::memory::Compactor` impl that
//! summarizes evicted conversation turns by calling the env-configured
//! LLM directly (via `core::agent::llm_client::chat_simple_with_timeout`).
//!
//! # Why rig-direct, not sidecar
//!
//! The Python sidecar no longer hosts an LLM endpoint — it serves
//! embed/rerank/VLM/MolDet/MolScribe only. Routing the compactor
//! through the sidecar would require reviving `/api/v1/llm/chat`,
//! duplicating the OpenAI/Anthropic HTTP code that already lives in
//! `llm_client.rs`. The compactor is non-critical (a missing LLM just
//! logs and skips), so the strict `MBFORGE_LLM_*` env requirement is
//! acceptable — see `llm_client::chat_simple_with_timeout`'s docstring.
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

use super::llm_client;

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

/// Compactor that delegates to the env-configured LLM (via
/// `llm_client::chat_simple_with_timeout`). Cheap to clone — the
/// underlying HTTP client is a process-wide singleton.
#[derive(Clone, Default)]
pub struct RigDirectCompactor;

impl RigDirectCompactor {
    pub fn new() -> Self {
        Self
    }

    /// 向后兼容旧调用方（`SidecarCompactor::new(url)`）。
    /// 旧版需要 sidecar URL；rig-direct 实现从 `MBFORGE_LLM_*` 环境变量读取，
    /// 因此传参被忽略。
    #[deprecated(note = "sidecar URL 不再需要，使用 `new()` 即可")]
    pub fn with_url(_sidecar_url: impl Into<String>) -> Self {
        let _ = _sidecar_url.into();
        Self
    }
}

/// 旧名兼容：保留 `SidecarCompactor` 类型别名，让现有调用方
/// （如 `MbforgeManagedMemory::compactor_kind()`）无需修改。
/// 内部已切换到 rig-direct 实现。
pub type SidecarCompactor = RigDirectCompactor;

impl Compactor for RigDirectCompactor {
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

            let user_prompt = format!(
                "请将以下对话压缩为一段不超过 200 字的中文摘要，保留关键事实（人名/数字/决定/待办）。\n\
                 如果对话为空，回复\"无内容\"。\n\n\
                 对话：\n{conversation}"
            );

            // 30 秒超时 — 压缩是后台任务，宁可跳过也不要阻塞 agent 主循环。
            // 调用 `llm_client::chat_simple_with_timeout` 而非构造自己的 HTTP 请求，
            // 与 memory/trajectory extraction 复用同一条 env-driven 代码路径。
            let text = llm_client::chat_simple_with_timeout(
                "你是一个对话压缩专家。",
                &user_prompt,
                30,
            )
            .await
            .map_err(|e| MemoryError::backend(format!("compactor LLM call: {e}")))?;

            Ok(SummaryArtifact { text: text.trim().to_string() })
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
    #[ignore = "needs MBFORGE_LLM_* env; covered by the integration test"]
    fn test_compactor_construction() {
        // The compactor no longer needs any URL — it pulls the LLM
        // endpoint from MBFORGE_LLM_* at call time, so the construction
        // path is a no-op. Kept as a smoke check that the type is
        // constructible without panicking.
        let _ = RigDirectCompactor::new();
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
