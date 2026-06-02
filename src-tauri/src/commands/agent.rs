use std::collections::HashMap;
use std::sync::Arc;
use tauri::Emitter;
use tokio::sync::RwLock;

use crate::core::constants::{EVT_AGENT_STREAM_CHUNK, EVT_AGENT_STREAM_DONE};

use crate::core::agent::Agent;
use crate::core::config::ModelConfig;
use crate::core::context::Message;

macro_rules! log_err {
    ($msg:expr) => {{
        let msg: &str = $msg;
        log::error!("{}", msg);
        msg.to_string()
    }};
    ($fmt:literal, $($arg:expr),+) => {{
        let msg = format!($fmt, $($arg),+);
        log::error!("{}", msg);
        msg
    }};
}

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
        .ok_or_else(|| log_err!("Agent not initialized, call agent_init first"))?;

    let root = project_root.as_deref().map(std::path::Path::new);
    let mut agent = Agent::new(config, sidecar_url, root);

    // 尝试加载之前保存的上下文（跨会话持久化）
    if agent.load_context() {
        log::info!("Agent session {}: loaded persisted context", session_id);
    }

    log::info!("Agent session created: {}", session_id);

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
        .ok_or_else(|| log_err!("agent_chat: session not found: {}", session_id))?;
    agent.chat(&user_input).await.map_err(|e| {
        log::error!("agent_chat failed for session={}: {}", session_id, e);
        e
    })
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
            .ok_or_else(|| log_err!("agent_chat_stream: session not found: {}", session_id))?;
        agent.chat_stream(&user_input).await.map_err(|e| {
            log::error!("agent_chat_stream failed for session={}: {}", session_id, e);
            e
        })?
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
            if let Err(e) = handle.emit(EVT_AGENT_STREAM_CHUNK, &payload) {
                log::error!("agent_chat_stream emit failed for session={}: {}", sid, e);
            }
        }
        if let Err(e) = handle.emit(
            EVT_AGENT_STREAM_DONE,
            serde_json::json!({ "session_id": sid }),
        ) {
            log::error!("agent_chat_stream done emit failed: {}", e);
        }
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
        .ok_or_else(|| log_err!("Agent not initialized, call agent_init first"))?;

    // 先保存旧 Agent 的上下文
    {
        let agents = state.agents.write().await;
        if let Some(old_agent) = agents.get(&session_id) {
            old_agent.save_context();
            log::info!(
                "Agent session {}: old context saved before switch",
                session_id
            );
        }
    }

    let root = std::path::Path::new(&project_root);
    let mut agent = Agent::new(config, sidecar_url, Some(root));
    agent.set_project_context(&project_name, &project_root);

    // 尝试加载新项目的上下文
    if agent.load_context() {
        log::info!(
            "Agent session {}: loaded context for new project {}",
            session_id,
            project_name
        );
    }

    log::info!(
        "Agent session switched project: {} -> {}",
        session_id,
        project_name
    );

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
        .ok_or_else(|| log_err!("agent_clear: session not found: {}", session_id))?;
    agent.clear();
    // 清除后删除持久化文件
    if let Some(ref root) = agent.project_root {
        let path = root.join(".mbforge/memory/agent_context.json");
        if path.exists() {
            let _ = std::fs::remove_file(&path);
            log::info!("Agent session {}: context file removed", session_id);
        }
    }
    log::info!("Agent session cleared: {}", session_id);
    Ok(())
}

#[tauri::command]
pub async fn agent_destroy_session(
    state: tauri::State<'_, AgentState>,
    session_id: String,
) -> Result<(), String> {
    let mut agents = state.agents.write().await;
    // 销毁前先保存上下文
    if let Some(agent) = agents.get(&session_id) {
        agent.save_context();
        log::info!("Agent session {}: context saved before destroy", session_id);
    }
    agents.remove(&session_id);
    Ok(())
}

#[tauri::command]
pub async fn agent_get_history(
    state: tauri::State<'_, AgentState>,
    session_id: String,
) -> Result<Vec<Message>, String> {
    let agents = state.agents.read().await;
    let agent = agents.get(&session_id).ok_or("Session not found")?;
    Ok(agent.context.get_history_messages())
}
