use std::sync::Arc;
use tokio::sync::RwLock;
use tauri::Emitter;

use crate::core::agent::Agent;
use crate::core::config::ModelConfig;
use crate::core::context::Message;

pub struct AgentState {
    pub inner: Arc<RwLock<Option<Agent>>>,
}

impl AgentState {
    pub fn new() -> Self {
        Self { inner: Arc::new(RwLock::new(None)) }
    }
}

#[tauri::command]
pub async fn agent_init(
    state: tauri::State<'_, AgentState>,
    config: ModelConfig,
    sidecar_url: String,
    project_root: Option<String>,
) -> Result<(), String> {
    let root = project_root.as_deref().map(std::path::Path::new);
    let agent = Agent::new(&config, &sidecar_url, root);
    let mut guard = state.inner.write().await;
    *guard = Some(agent);
    Ok(())
}

#[tauri::command]
pub async fn agent_chat(
    state: tauri::State<'_, AgentState>,
    user_input: String,
) -> Result<String, String> {
    let mut guard = state.inner.write().await;
    let agent = guard.as_mut().ok_or("Agent not initialized")?;
    agent.chat(&user_input).await
}

#[tauri::command]
pub async fn agent_chat_stream(
    state: tauri::State<'_, AgentState>,
    app: tauri::AppHandle,
    user_input: String,
) -> Result<(), String> {
    let rx = {
        let mut guard = state.inner.write().await;
        let agent = guard.as_mut().ok_or("Agent not initialized")?;
        agent.chat_stream(&user_input).await?
    };

    let handle = app.clone();
    tokio::spawn(async move {
        let mut rx = rx;
        while let Some(chunk) = rx.recv().await {
            let _ = handle.emit("agent-stream-chunk", &chunk);
        }
        let _ = handle.emit("agent-stream-done", ());
    });
    Ok(())
}

#[tauri::command]
pub async fn agent_switch_project(
    state: tauri::State<'_, AgentState>,
    config: ModelConfig,
    sidecar_url: String,
    project_root: String,
    project_name: String,
) -> Result<(), String> {
    let root = std::path::Path::new(&project_root);
    let mut agent = Agent::new(&config, &sidecar_url, Some(root));
    agent.set_project_context(&project_name, &project_root);
    let mut guard = state.inner.write().await;
    *guard = Some(agent);
    Ok(())
}

#[tauri::command]
pub async fn agent_clear(
    state: tauri::State<'_, AgentState>,
) -> Result<(), String> {
    let mut guard = state.inner.write().await;
    let agent = guard.as_mut().ok_or("Agent not initialized")?;
    agent.clear();
    Ok(())
}

#[tauri::command]
pub async fn agent_get_history(
    state: tauri::State<'_, AgentState>,
) -> Result<Vec<Message>, String> {
    let guard = state.inner.read().await;
    let agent = guard.as_ref().ok_or("Agent not initialized")?;
    let msgs = agent.context.get_history_messages();
    Ok(msgs)
}
