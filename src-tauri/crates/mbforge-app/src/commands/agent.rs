//! Agent session management Tauri commands.
//!
//! Owns an in-memory session store keyed by `session_id`. Each session keeps
//! the running message history plus the bound `project_root` / `project_name`
//! so switching projects keeps the conversation alive.
//!
//! Chat completion routes through
//! `mbforge_pipeline::structure::post_process::call_llm_api_async` — the same
//! provider dispatch (OpenAI-compatible / DeepSeek / Ollama) used by the PDF
//! post-processor. No new HTTP plumbing.
//!
//! Streaming emits `agent-stream-chunk` and `agent-stream-done` events on the
//! Tauri app handle. The frontend `EVT.AgentStreamChunk` / `EVT.AgentStreamDone`
//! constants must match the `EVT_AGENT_STREAM_CHUNK` / `EVT_AGENT_STREAM_DONE`
//! constants in `mbforge_infra::config::constants`.
//!
//! History is intentionally non-persistent: sessions live for the lifetime of
//! the Tauri process. Persisting to disk would re-introduce the issues
//! `archived/agent/src/conversation_store.rs` dealt with (concurrent file
//! writes, schema migration), which are out of scope for this fix.

use std::collections::HashMap;
use std::sync::Mutex;

use mbforge_infra::config::constants::{
    EVT_AGENT_STREAM_CHUNK, EVT_AGENT_STREAM_DONE,
};
use mbforge_pipeline::structure::post_process::{call_llm_api, call_llm_api_async};
use serde::Serialize;
use tauri::{AppHandle, Emitter, State};

/// One message in a session's running history.
#[derive(Clone, Debug, Serialize)]
pub struct ChatMessage {
    /// `"user"` or `"assistant"`.
    pub role: String,
    /// Plain-text body.
    pub content: String,
}

/// Session-scoped state: message history + the project the conversation was
/// opened against. `project_root == None` means the agent is in chat-only
/// mode (no project binding); calls like `agent_chat` still work.
#[derive(Default)]
pub struct AgentSession {
    pub messages: Vec<ChatMessage>,
    pub project_root: Option<String>,
    pub project_name: Option<String>,
}

/// Shared state — one map per Tauri process.
#[derive(Default)]
pub struct AgentSessionState {
    pub sessions: Mutex<HashMap<String, AgentSession>>,
}

const SYSTEM_PROMPT_BASE: &str = "You are MBForge Agent, an assistant for molecular science and drug discovery. \
Answer concisely and cite specific molecules, documents, or KB results when available.";

const CHAT_STREAM_CHUNK_CHARS: usize = 24;

/// Build the system prompt for a chat turn. Includes the project binding so
/// the LLM has context but does not leak the project name into the user-visible
/// turn log.
fn build_system_prompt(session: &AgentSession) -> String {
    match (&session.project_root, &session.project_name) {
        (Some(root), Some(name)) => format!(
            "{SYSTEM_PROMPT_BASE} Current project: \"{name}\" (root: {root})."
        ),
        _ => SYSTEM_PROMPT_BASE.to_string(),
    }
}

/// Concatenate the message history into a single user-side prompt. The full
/// multi-turn context is forwarded every call because the local LLM providers
/// we use do not support server-side chat state.
fn build_user_prompt(history: &[ChatMessage], new_user: &str) -> String {
    let mut out = String::new();
    for msg in history {
        match msg.role.as_str() {
            "user" => {
                out.push_str("User: ");
                out.push_str(&msg.content);
                out.push('\n');
            }
            "assistant" => {
                out.push_str("Assistant: ");
                out.push_str(&msg.content);
                out.push('\n');
            }
            _ => {}
        }
    }
    out.push_str("User: ");
    out.push_str(new_user);
    out.push_str("\nAssistant:");
    out
}

/// Initialize the agent subsystem. The LLM has no per-session override —
/// the global LLM env config (Settings UI) takes precedence. `sidecar_url`
/// is accepted for API symmetry with the archived contract but not used
/// here; we route through the same LLM dispatch the PDF pipeline uses.
#[tauri::command]
pub fn agent_init(
    _sidecar_url: String,
    state: State<'_, AgentSessionState>,
) -> Result<(), String> {
    let mut guard = state
        .sessions
        .lock()
        .map_err(|e| format!("agent session lock poisoned: {e}"))?;
    guard.clear();
    Ok(())
}

/// Create a new conversation session. `project_root` is optional; if omitted
/// the session is unbound (chat-only mode).
#[tauri::command]
pub fn agent_create_session(
    session_id: String,
    project_root: Option<String>,
    state: State<'_, AgentSessionState>,
) -> Result<(), String> {
    let mut guard = state
        .sessions
        .lock()
        .map_err(|e| format!("agent session lock poisoned: {e}"))?;
    guard.insert(
        session_id,
        AgentSession {
            messages: Vec::new(),
            project_root,
            project_name: None,
        },
    );
    Ok(())
}

/// Synchronous chat — returns the full response as a string.
#[tauri::command]
pub async fn agent_chat(
    session_id: String,
    user_input: String,
    state: State<'_, AgentSessionState>,
) -> Result<String, String> {
    if user_input.trim().is_empty() {
        return Err("user_input is empty".into());
    }
    let (system, prompt) = {
        let mut guard = state
            .sessions
            .lock()
            .map_err(|e| format!("agent session lock poisoned: {e}"))?;
        let session = guard
            .get_mut(&session_id)
            .ok_or_else(|| format!("agent session {session_id:?} not found"))?;
        session.messages.push(ChatMessage {
            role: "user".into(),
            content: user_input.clone(),
        });
        let system = build_system_prompt(session);
        let prompt = build_user_prompt(&session.messages, &user_input);
        (system, prompt)
    };

    let (reply, _tokens) = call_llm_api_async(&system, &prompt).await?;

    {
        let mut guard = state
            .sessions
            .lock()
            .map_err(|e| format!("agent session lock poisoned: {e}"))?;
        if let Some(session) = guard.get_mut(&session_id) {
            session.messages.push(ChatMessage {
                role: "assistant".into(),
                content: reply.clone(),
            });
        }
    }
    Ok(reply)
}

/// Streaming chat. Emits `agent-stream-chunk` events as the response is
/// accumulated, then `agent-stream-done` on completion. The chunking is
/// word-boundary based — characters are buffered until a whitespace
/// appears or the buffer reaches `CHAT_STREAM_CHUNK_CHARS`.
///
/// This is a fallback strategy: the local LLM providers do not support
/// incremental tokens, so we surface completion in coarse chunks rather
/// than waiting for the full reply. Frontend listeners filter by
/// `session_id` to keep concurrent sessions isolated.
#[tauri::command]
pub async fn agent_chat_stream(
    session_id: String,
    user_input: String,
    app: AppHandle,
    state: State<'_, AgentSessionState>,
) -> Result<(), String> {
    if user_input.trim().is_empty() {
        return Err("user_input is empty".into());
    }
    let (system, prompt) = {
        let mut guard = state
            .sessions
            .lock()
            .map_err(|e| format!("agent session lock poisoned: {e}"))?;
        let session = guard
            .get_mut(&session_id)
            .ok_or_else(|| format!("agent session {session_id:?} not found"))?;
        session.messages.push(ChatMessage {
            role: "user".into(),
            content: user_input.clone(),
        });
        let system = build_system_prompt(session);
        let prompt = build_user_prompt(&session.messages, &user_input);
        (system, prompt)
    };

    // call_llm_api is itself sync and manages a tokio runtime internally,
    // so we can call it directly from inside spawn_blocking without an
    // extra await.
    let reply = tokio::task::spawn_blocking(move || call_llm_api(&system, &prompt).map(|(c, _)| c))
        .await
        .map_err(|e| format!("chat task join error: {e}"))??;

    // Append to history and emit in coarse chunks.
    {
        let mut guard = state
            .sessions
            .lock()
            .map_err(|e| format!("agent session lock poisoned: {e}"))?;
        if let Some(session) = guard.get_mut(&session_id) {
            session.messages.push(ChatMessage {
                role: "assistant".into(),
                content: reply.clone(),
            });
        }
    }

    let mut buffer = String::new();
    for ch in reply.chars() {
        buffer.push(ch);
        let flush = buffer.chars().count() >= CHAT_STREAM_CHUNK_CHARS || ch.is_whitespace();
        if flush {
            let payload = AgentStreamChunkPayload {
                session_id: session_id.clone(),
                delta: buffer.clone(),
                finish_reason: None,
            };
            let _ = app.emit(EVT_AGENT_STREAM_CHUNK, payload);
            buffer.clear();
        }
    }
    if !buffer.is_empty() {
        let payload = AgentStreamChunkPayload {
            session_id: session_id.clone(),
            delta: buffer,
            finish_reason: None,
        };
        let _ = app.emit(EVT_AGENT_STREAM_CHUNK, payload);
    }

    let done = AgentStreamDonePayload {
        session_id: session_id.clone(),
    };
    let _ = app.emit(EVT_AGENT_STREAM_DONE, done);
    Ok(())
}

/// Rebind a session to a different project. Preserves message history.
#[tauri::command]
pub fn agent_switch_project(
    session_id: String,
    project_root: String,
    project_name: String,
    state: State<'_, AgentSessionState>,
) -> Result<(), String> {
    let mut guard = state
        .sessions
        .lock()
        .map_err(|e| format!("agent session lock poisoned: {e}"))?;
    let session = guard
        .get_mut(&session_id)
        .ok_or_else(|| format!("agent session {session_id:?} not found"))?;
    session.project_root = Some(project_root);
    session.project_name = Some(project_name);
    Ok(())
}

/// Drop message history but keep the session + project binding.
#[tauri::command]
pub fn agent_clear(
    session_id: String,
    state: State<'_, AgentSessionState>,
) -> Result<(), String> {
    let mut guard = state
        .sessions
        .lock()
        .map_err(|e| format!("agent session lock poisoned: {e}"))?;
    let session = guard
        .get_mut(&session_id)
        .ok_or_else(|| format!("agent session {session_id:?} not found"))?;
    session.messages.clear();
    Ok(())
}

/// Destroy a session entirely.
#[tauri::command]
pub fn agent_destroy_session(
    session_id: String,
    state: State<'_, AgentSessionState>,
) -> Result<(), String> {
    let mut guard = state
        .sessions
        .lock()
        .map_err(|e| format!("agent session lock poisoned: {e}"))?;
    guard.remove(&session_id);
    Ok(())
}

/// Return the message history of a session, oldest first.
#[tauri::command]
pub fn agent_get_history(
    session_id: String,
    state: State<'_, AgentSessionState>,
) -> Result<Vec<ChatMessage>, String> {
    let guard = state
        .sessions
        .lock()
        .map_err(|e| format!("agent session lock poisoned: {e}"))?;
    let session = guard
        .get(&session_id)
        .ok_or_else(|| format!("agent session {session_id:?} not found"))?;
    Ok(session.messages.clone())
}

#[derive(Clone, Debug, Serialize)]
struct AgentStreamChunkPayload {
    session_id: String,
    delta: String,
    finish_reason: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
struct AgentStreamDonePayload {
    session_id: String,
}
