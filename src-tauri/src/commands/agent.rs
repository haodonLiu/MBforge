use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use tauri::Emitter;

use crate::core::agent::Agent;
use crate::core::config::ModelConfig;
use crate::core::context::Message;

pub struct AgentState {
    pub agents: Arc<RwLock<HashMap<String, Agent>>>,
    pub default_config: Arc<RwLock<Option<(ModelConfig, String)>>>,
}

impl AgentState {
    pub fn new() -> Self {
        Self {
            agents: Arc::new(RwLock::new(HashMap::new())),
            default_config: Arc::new(RwLock::new(None)),
        }
    }
}

#[tauri::command]
pub async fn agent_init(
    state: tauri::State<'_, AgentState>,
    config: ModelConfig,
    sidecar_url: String,
) -> Result<(), String> {
    let mut guard = state.default_config.write().await;
    *guard = Some((config, sidecar_url));
    Ok(())
}

#[tauri::command]
pub async fn agent_create_session(
    state: tauri::State<'_, AgentState>,
    session_id: String,
    project_root: Option<String>,
) -> Result<(), String> {
    let config_guard = state.default_config.read().await;
    let (config, sidecar_url) = config_guard
        .as_ref()
        .ok_or("Agent not initialized, call agent_init first")?;

    let root = project_root.as_deref().map(std::path::Path::new);
    let agent = Agent::new(config, sidecar_url, root);

    let mut agents = state.agents.write().await;
    agents.insert(session_id, agent);
    Ok(())
}

#[tauri::command]
pub async fn agent_chat(
    state: tauri::State<'_, AgentState>,
    session_id: String,
    user_input: String,
) -> Result<String, String> {
    let mut agents = state.agents.write().await;
    let agent = agents
        .get_mut(&session_id)
        .ok_or("Session not found")?;
    agent.chat(&user_input).await
}

#[tauri::command]
pub async fn agent_chat_stream(
    state: tauri::State<'_, AgentState>,
    app: tauri::AppHandle,
    session_id: String,
    user_input: String,
) -> Result<(), String> {
    let rx = {
        let mut agents = state.agents.write().await;
        let agent = agents
            .get_mut(&session_id)
            .ok_or("Session not found")?;
        agent.chat_stream(&user_input).await?
    };

    let handle = app.clone();
    let sid = session_id.clone();
    tokio::spawn(async move {
        let mut rx = rx;
        while let Some(chunk) = rx.recv().await {
            let payload = serde_json::json!({
                "session_id": sid,
                "delta": chunk.delta,
                "finish_reason": chunk.finish_reason,
            });
            let _ = handle.emit("agent-stream-chunk", &payload);
        }
        let _ = handle.emit("agent-stream-done", serde_json::json!({ "session_id": sid }));
    });
    Ok(())
}

#[tauri::command]
pub async fn agent_switch_project(
    state: tauri::State<'_, AgentState>,
    session_id: String,
    project_root: String,
    project_name: String,
) -> Result<(), String> {
    let config_guard = state.default_config.read().await;
    let (config, sidecar_url) = config_guard
        .as_ref()
        .ok_or("Agent not initialized, call agent_init first")?;

    let root = std::path::Path::new(&project_root);
    let mut agent = Agent::new(config, sidecar_url, Some(root));
    agent.set_project_context(&project_name, &project_root);

    let mut agents = state.agents.write().await;
    agents.insert(session_id, agent);
    Ok(())
}

#[tauri::command]
pub async fn agent_clear(
    state: tauri::State<'_, AgentState>,
    session_id: String,
) -> Result<(), String> {
    let mut agents = state.agents.write().await;
    let agent = agents
        .get_mut(&session_id)
        .ok_or("Session not found")?;
    agent.clear();
    Ok(())
}

#[tauri::command]
pub async fn agent_destroy_session(
    state: tauri::State<'_, AgentState>,
    session_id: String,
) -> Result<(), String> {
    let mut agents = state.agents.write().await;
    agents.remove(&session_id);
    Ok(())
}

#[tauri::command]
pub async fn agent_get_history(
    state: tauri::State<'_, AgentState>,
    session_id: String,
) -> Result<Vec<Message>, String> {
    let agents = state.agents.read().await;
    let agent = agents
        .get(&session_id)
        .ok_or("Session not found")?;
    Ok(agent.context.get_history_messages())
}
