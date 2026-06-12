#![allow(dead_code)]
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use futures::StreamExt;
use tauri::Emitter;
use tokio::sync::RwLock;

use crate::core::constants::{EVT_AGENT_STREAM_CHUNK, EVT_AGENT_STREAM_DONE};

use crate::core::agent::compactor::SidecarCompactor;
use crate::core::agent::context::{LayeredContext, Message};
use crate::core::agent::conversation_store::SqliteConversationMemory;
use crate::core::agent::demotion::EpisodicDemotionHook;
use crate::core::agent::managed_memory::MbforgeManagedMemory;
use crate::core::agent::observability::AuditLog;
use crate::core::agent::rig_adapter::{
    ConcreteHook, MbforgeAgent, MbforgeAgentSpec, MbforgeProviderConfig, MbforgeProviderKind,
    MbforgeStreamItem,
};
use crate::core::agent::rig_hooks::{AuditLogHook, TrajectoryHook};
use crate::core::agent::rig_memory::{
    CompositeMemory, MemoryManagerMemory, MbforgeConversationMemory, SkillsManagerMemory,
};
use crate::core::agent::trajectory::TrajectoryTracker;
use crate::core::config::constants::PROJECT_META_DIR;

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

/// 长时记忆 / 工具调用上下文的会话单元 — 取代老的 `Agent` 平铺字段。
///
/// 字段说明：
/// - `agent`：rig 适配器暴露的 `prompt` / `stream` 入口
/// - `context`：保留 `LayeredContext` 以便 `save_to_file` / `load_from_file` /
///   `get_history_messages` 这类与 LLM 无关的能力继续工作
/// - `memory`：以 `Arc` 持有，让 `tokio::spawn` 的 fire-and-forget
///   `observe_turn` 拿得到一个拥有所有权的句柄
/// - `audit` / `trajectory`：以 `Arc` 持有，让 rig hook 在 LLM 循环里共享同一份
///   文件 / 内存存储
/// - `project_root`：决定上下文文件 `<root>/.mbforge/memory/agent_context.json`
///   的写入位置
pub struct AgentSession {
    pub agent: MbforgeAgent,
    pub context: LayeredContext,
    pub memory: Arc<CompositeMemory>,
    pub sidecar_url: String,
    pub audit: Option<Arc<AuditLog>>,
    pub trajectory: Option<Arc<Mutex<TrajectoryTracker>>>,
    pub audit_hook: Option<AuditLogHook>,
    pub trajectory_hook: Option<TrajectoryHook>,
    pub project_root: Option<PathBuf>,
}

impl AgentSession {
    fn context_path(&self) -> Option<PathBuf> {
        self.project_root
            .as_ref()
            .map(|root| root.join(PROJECT_META_DIR).join("memory").join("agent_context.json"))
    }

    fn save_context(&self) {
        if let Some(path) = self.context_path() {
            if let Err(e) = self.context.save_to_file(&path) {
                log::error!("save_context failed for {:?}: {}", path, e);
            } else {
                log::info!("Agent session context saved to {:?}", path);
            }
        }
    }

    fn load_context(&mut self) -> bool {
        if let Some(path) = self.context_path() {
            if let Some(loaded) = LayeredContext::load_from_file(&path) {
                // 保留本会话已构建的 system prompt（rig preamble 已注入
                // memory / skills），其余层用磁盘上的版本覆盖。
                let new_system = self.context.get_system_prompt();
                let mut ctx = loaded;
                ctx.set_system_prompt(&new_system);
                self.context = ctx;
                return true;
            }
        }
        false
    }

    fn clear(&mut self) {
        self.context.clear_history();
        if let Some(path) = self.context_path() {
            if path.exists() {
                if let Err(e) = std::fs::remove_file(&path) {
                    log::error!("clear: remove_file {:?} failed: {}", path, e);
                } else {
                    log::info!("Agent session context file removed: {:?}", path);
                }
            }
        }
    }
}

pub struct AgentState {
    pub agents: Arc<RwLock<HashMap<String, AgentSession>>>,
    /// Sidecar URL only — LLM config is env-driven (`MBFORGE_LLM_*`) and
    /// read fresh per session via `MbforgeProviderConfig::from_app_config()`.
    pub default_sidecar: Arc<RwLock<Option<String>>>,
}

impl AgentState {
    pub fn new() -> Self {
        Self {
            agents: Arc::new(RwLock::new(HashMap::new())),
            default_sidecar: Arc::new(RwLock::new(None)),
        }
    }
}

#[tauri::command]
pub async fn agent_init(
    state: tauri::State<'_, AgentState>,
    sidecar_url: String,
) -> Result<(), String> {
    let mut guard = state.default_sidecar.write().await;
    *guard = Some(sidecar_url);
    Ok(())
}

#[tauri::command]
pub async fn agent_create_session(
    state: tauri::State<'_, AgentState>,
    session_id: String,
    project_root: Option<String>,
) -> Result<(), String> {
    let sidecar_url = {
        let guard = state.default_sidecar.read().await;
        guard
            .as_ref()
            .ok_or_else(|| log_err!("Agent not initialized, call agent_init first"))?
            .clone()
    };

    let root_path = project_root.as_ref().map(PathBuf::from);
    let mut session = create_session_for_config(
        &sidecar_url,
        root_path.as_deref(),
        &session_id,
    )
    .await
        .map_err(|e| {
            log::error!("agent_create_session: create_session_for_config failed: {}", e);
            e
        })?;

    if session.load_context() {
        log::info!("Agent session {}: loaded persisted context", session_id);
    }

    log::info!("Agent session created: {}", session_id);

    let mut agents = state.agents.write().await;
    agents.insert(session_id, session);
    Ok(())
}

#[tauri::command]
pub async fn agent_chat(
    state: tauri::State<'_, AgentState>,
    session_id: String,
    user_input: String,
) -> Result<String, String> {
    // 先取出 prompt() 所需的所有 owned 句柄，再释放 sessions 读锁，
    // 避免在等 LLM 响应时阻塞其他会话。`MbforgeAgent` 内部 rig agent 用
    // `Arc<M>` 共享模型，clone 廉价。
    let (memory, agent) = {
        let agents = state.agents.read().await;
        let session = agents
            .get(&session_id)
            .ok_or_else(|| log_err!("agent_chat: session not found: {}", session_id))?;
        (Arc::clone(&session.memory), session.agent.clone())
    };

    let cid = crate::core::agent::session_id::SessionId::from(session_id.as_str());
    let result = agent.prompt(&cid, &user_input).await.map_err(|e| {
        log::error!("agent_chat failed for session={}: {}", session_id, e);
        e
    })?;

    // Fire-and-forget：复制到堆上再 spawn，让 observe_turn 异步跑记忆 / 技能
    // 抽取。`Arc<CompositeMemory>` 是 Send + Sync，trait 返回的 `Pin<Box<dyn
    // Future<Output = ()> + Send>>` 借用 spawn 闭包里的 `&Arc<…>` — Arc 本身
    // 是 `'static`，所以 future 满足 `'static` 约束。
    let memory_for_observe = Arc::clone(&memory);
    let user_input_owned = user_input.clone();
    let result_owned = result.clone();
    tokio::spawn(async move {
        let _ = memory_for_observe
            .observe_turn(&user_input_owned, &result_owned)
            .await;
    });

    Ok(result)
}

#[tauri::command]
pub async fn agent_chat_stream(
    state: tauri::State<'_, AgentState>,
    app: tauri::AppHandle,
    session_id: String,
    user_input: String,
) -> Result<(), String> {
    let (memory, stream) = {
        let agents = state.agents.read().await;
        let session = agents
            .get(&session_id)
            .ok_or_else(|| log_err!("agent_chat_stream: session not found: {}", session_id))?;
        let cid = crate::core::agent::session_id::SessionId::from(session_id.as_str());
        (
            Arc::clone(&session.memory),
            session.agent.stream(&cid, &user_input),
        )
    };

    let handle = app.clone();
    let sid = session_id.clone();
    let user_input_owned = user_input.clone();
    tokio::spawn(async move {
        let mut stream = stream;
        let mut final_text: Option<String> = None;
        while let Some(item) = stream.next().await {
            match item {
                Ok(MbforgeStreamItem::TextDelta(delta)) => {
                    let payload = serde_json::json!({
                        "session_id": sid,
                        "delta": delta,
                        "finish_reason": Option::<String>::None,
                    });
                    if let Err(e) = handle.emit(EVT_AGENT_STREAM_CHUNK, &payload) {
                        log::error!(
                            "agent_chat_stream emit EVT_AGENT_STREAM_CHUNK failed for session={}: {}",
                            sid,
                            e
                        );
                    }
                }
                Ok(MbforgeStreamItem::ToolCall { id, name, arguments }) => {
                    log::debug!(
                        "agent_chat_stream session={} tool_call id={} name={} args={}",
                        sid,
                        id,
                        name,
                        arguments
                    );
                }
                Ok(MbforgeStreamItem::ToolResult { id, name, result }) => {
                    log::debug!(
                        "agent_chat_stream session={} tool_result id={} name={} len={}",
                        sid,
                        id,
                        name,
                        result.len()
                    );
                }
                Ok(MbforgeStreamItem::Final {
                    content,
                    prompt_tokens,
                    completion_tokens,
                }) => {
                    final_text = Some(content.clone());
                    let payload = serde_json::json!({
                        "session_id": sid,
                        "content": content,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                    });
                    if let Err(e) = handle.emit(EVT_AGENT_STREAM_DONE, &payload) {
                        log::error!(
                            "agent_chat_stream emit EVT_AGENT_STREAM_DONE failed for session={}: {}",
                            sid,
                            e
                        );
                    }
                }
                Err(e) => {
                    log::error!("agent_chat_stream session={} stream error: {}", sid, e);
                    let payload = serde_json::json!({
                        "session_id": sid,
                        "error": e,
                    });
                    if let Err(emit_err) = handle.emit(EVT_AGENT_STREAM_DONE, &payload) {
                        log::error!(
                            "agent_chat_stream done emit failed after error: {}",
                            emit_err
                        );
                    }
                    break;
                }
            }
        }
        // Fire-and-forget `observe_turn` after the stream completes
        // (whether the final event was a `Final` or an `Err`). This
        // mirrors the `agent_chat` path — fixes the bug where the
        // streaming sibling silently skipped long-term memory
        // extraction. If the stream errored before the LLM produced
        // any text, `final_text` is None and `observe_turn` sees an
        // empty assistant output, which the trait short-circuits on.
        if let Some(text) = final_text {
            let memory_for_observe = Arc::clone(&memory);
            tokio::spawn(async move {
                let _ = memory_for_observe
                    .observe_turn(&user_input_owned, &text)
                    .await;
            });
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
    let sidecar_url = {
        let guard = state.default_sidecar.read().await;
        guard
            .as_ref()
            .ok_or_else(|| log_err!("Agent not initialized, call agent_init first"))?
            .clone()
    };

    // 先保存旧 Agent 的上下文
    {
        let agents = state.agents.read().await;
        if let Some(old) = agents.get(&session_id) {
            old.save_context();
            log::info!(
                "Agent session {}: old context saved before switch",
                session_id
            );
        }
    }

    let root_path = PathBuf::from(&project_root);
    let mut session =
        create_session_for_config(&sidecar_url, Some(&root_path), &session_id)
            .await
            .map_err(|e| {
                log::error!(
                    "agent_switch_project: create_session_for_config failed: {}",
                    e
                );
                e
            })?;
    session
        .context
        .set_project_context(&format!("项目: {}\n路径: {}", project_name, project_root));

    if session.load_context() {
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
    agents.insert(session_id, session);
    Ok(())
}

#[tauri::command]
pub async fn agent_clear(
    state: tauri::State<'_, AgentState>,
    session_id: String,
) -> Result<(), String> {
    let mut agents = state.agents.write().await;
    let session = agents
        .get_mut(&session_id)
        .ok_or_else(|| log_err!("agent_clear: session not found: {}", session_id))?;
    session.clear();
    log::info!("Agent session cleared: {}", session_id);
    Ok(())
}

#[tauri::command]
pub async fn agent_destroy_session(
    state: tauri::State<'_, AgentState>,
    session_id: String,
) -> Result<(), String> {
    let mut agents = state.agents.write().await;
    if let Some(session) = agents.get(&session_id) {
        session.save_context();
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
    let session = agents
        .get(&session_id)
        .ok_or("Session not found")?;
    // The conversation history now lives in
    // `SqliteConversationMemory` (keyed by `session_id`) rather than
    // in `LayeredContext.history` (which is dead code). We still
    // return the MBForge `Message` shape so the frontend doesn't
    // need to change.
    let cid = crate::core::agent::session_id::SessionId::from(session_id.as_str());
    session.agent.history(&cid).await
}

/// 读取项目审计日志。
///
/// # Arguments
/// - `project_root`: 项目根目录；审计日志在 `<root>/.mbforge/audit.jsonl`
/// - `trace_id`: 可选 — 若提供，仅返回匹配的条目
/// - `limit`: 最多返回条数（默认 200）
#[tauri::command]
pub async fn audit_log_get(
    state: tauri::State<'_, AgentState>,
    project_root: String,
    session_id: Option<String>,
    trace_id: Option<String>,
    limit: Option<usize>,
) -> Result<Vec<crate::core::agent::observability::AuditEntry>, String> {
    use crate::core::agent::observability::AuditLog;
    let limit = limit.unwrap_or(200);

    // 1. 优先用 session 内存里的 audit（未刷盘的最快读路径）
    if let Some(sid) = session_id.as_ref() {
        if let Some(audit) = session_audit(&state, sid).await {
            let entries = match trace_id {
                Some(tid) => audit.read_by_trace(&tid, limit)?,
                None => {
                    let mut all = audit.read_all()?;
                    all.reverse();
                    all.truncate(limit);
                    all
                }
            };
            return Ok(entries);
        }
    }

    // 2. Fallback：从磁盘读（兼容无 session_id 或 session 没建 audit 的情况）
    let log = AuditLog::new(Path::new(&project_root))?;
    match trace_id {
        Some(tid) => log.read_by_trace(&tid, limit),
        None => {
            let mut all = log.read_all()?;
            all.reverse();
            all.truncate(limit);
            Ok(all)
        }
    }
}

/// Helper：从 `AgentState` 中按 `session_id` 取出 session 的 in-memory audit。
async fn session_audit(
    state: &tauri::State<'_, AgentState>,
    session_id: &str,
) -> Option<std::sync::Arc<crate::core::agent::observability::AuditLog>> {
    let agents = state.agents.read().await;
    agents.get(session_id).and_then(|s| s.audit.clone())
}

// ============================================================================
// 会话构造助手 — 取代 `Agent::new(config, sidecar_url, project_root)`
// ============================================================================

/// Construct a new rig agent + `LayeredContext` / long-term memory /
/// audit / trajectory, all driven by **env** (no per-session overrides).
///
/// Provider kind, base URL, API key, model name all come from
/// `MBFORGE_LLM_*` env vars via `MbforgeProviderConfig::from_app_config()`.
/// Sampling params (max_tokens / temperature) also come from env
/// (`MBFORGE_LLM_MAX_TOKENS` / `MBFORGE_LLM_TEMPERATURE`) — the Settings
/// UI cannot override them.
pub async fn create_session_for_config(
    sidecar_url: &str,
    project_root: Option<&Path>,
    session_id: &str,
) -> Result<AgentSession, String> {
    let cfg = MbforgeProviderConfig::from_app_config()?;

    // 1. Construct spec (rig adapter requires a system prompt + max_turns)
    let mut spec = MbforgeAgentSpec::general();
    if let Ok(v) = std::env::var("MBFORGE_LLM_MAX_TOKENS") {
        if let Ok(n) = v.trim().parse::<u64>() {
            if n > 0 {
                spec.max_tokens = Some(n);
            }
        }
    }
    if let Ok(v) = std::env::var("MBFORGE_LLM_TEMPERATURE") {
        if let Ok(t) = v.trim().parse::<f64>() {
            if t > 0.0 {
                spec.temperature = Some(t);
            }
        }
    }

    // 2. 在有 project_root 的情况下拉起长时记忆 / 技能 / 审计 / 轨迹
    let (memory, audit, trajectory, audit_hook, trajectory_hook) = if let Some(root) = project_root
    {
        // 复合记忆实例（供 `tokio::spawn(observe_turn)` 复用）。
        // 长时记忆 + 技能摘要的 system-prompt 注入由
        // `composite.inject_into_system_prompt()` 统一负责（取代
        // 此处原先手写拼接 `[用户记忆]…[Agent 经验]…[已掌握的技能]…`
        // 的逻辑——后者是 M5 临时方案，M6 后注入路径应走 trait）。
        let composite = Arc::new(CompositeMemory {
            memory: Some(MemoryManagerMemory::new(root)),
            skills: Some(SkillsManagerMemory::new(root)),
        });

        // 通过 trait 抽取 L1 长程记忆 + 技能摘要 → 预烤进 spec preamble
        let mem_injected = composite.inject_into_system_prompt().await;
        // 给 spec 一个最小功能 preamble（rig 端要求非空）
        spec.system_prompt = if mem_injected.trim().is_empty() {
            "你是 MBForge 分子科学 AI 助手，服务于药物化学与分子生物学研究。".to_string()
        } else {
            mem_injected
        };

        // 审计日志：失败时静默退化为 None（不阻断会话创建）
        let audit = match AuditLog::new(root) {
            Ok(a) => Some(Arc::new(a)),
            Err(e) => {
                log::warn!(
                    "create_session_for_config: AuditLog::new failed for {:?}: {}",
                    root,
                    e
                );
                None
            }
        };
        let audit_hook = audit
            .as_ref()
            .map(|arc| AuditLogHook::new(Arc::clone(arc)));

        // 轨迹追踪：构造即可（内部会自己 create_dir_all）。先
        // 持 `Arc<Mutex<…>>` 再 `from_arc` 复用同一份存储给 hook 与 session。
        let traj = Arc::new(Mutex::new(TrajectoryTracker::new(root)));
        let trajectory_hook = Some(TrajectoryHook::from_arc(Arc::clone(&traj)));

        (
            composite,
            audit,
            Some(traj),
            audit_hook,
            trajectory_hook,
        )
    } else {
        // 无 project_root：rig 仍可用，但记忆 / 审计 / 轨迹全部走 None
        if spec.system_prompt.is_empty() {
            spec.system_prompt =
                "你是 MBForge 分子科学 AI 助手，服务于药物化学与分子生物学研究。".into();
        }
        let composite = Arc::new(CompositeMemory {
            memory: None,
            skills: None,
        });
        (composite, None, None, None, None)
    };
    // 3. 构造 `MbforgeAgent`
    // O-05：传递项目级 hook（audit + trajectory 复用 session 已有的实例），
    //       保证 LLM 循环写到项目根的 `.mbforge/audit.jsonl`。
    //       audit 创建失败或无 project_root 时传 None，fallback 到临时 hook。
    //       clone 是廉价的：内部 Arc refcount +1。
    let project_hook = match (audit_hook.clone(), trajectory_hook.clone()) {
        (Some(a), Some(t)) => Some(ConcreteHook {
            audit: a,
            trajectory: t,
        }),
        _ => None,
    };
    // 3b. Build the rig `ConversationMemory` backend. With a real
    //     `project_root` we use `SqliteConversationMemory` (persists
    //     turns across restarts). Without one (e.g. tests, transient
    //     one-shot calls) we fall back to rig's built-in
    //     `InMemoryConversationMemory` wrapped in our managed layer
    //     so the wrapper code path is exercised either way.
    let managed_memory: Arc<MbforgeManagedMemory> = match project_root.as_ref() {
        Some(root) => {
            let sqlite = Arc::new(
                SqliteConversationMemory::open(Path::new(root))
                    .map_err(|e| format!("open conversations.db: {e}"))?,
            );
            // 旧 `SidecarCompactor::new(sidecar_url)` 已迁移为 rig-direct；
            // URL 参数被忽略。保留变量名以便与上下文一致。
            let _ = sidecar_url;
            let compactor = Arc::new(SidecarCompactor::new());
            let demotion = Arc::new(EpisodicDemotionHook::new(
                sqlite.conn_clone(),
                session_id.to_string(),
            ));
            let trait_handle: Arc<dyn rig_core::memory::ConversationMemory> =
                Arc::clone(&sqlite) as _;
            Arc::new(
                MbforgeManagedMemory::new_with_sqlite(trait_handle, Arc::clone(&sqlite))
                    .with_compactor(compactor)
                    .with_demotion(demotion),
            )
        }
        None => {
            // Fallback: rig's in-memory backend, wrapped so the
            // wrapper code path is identical to the production one
            // (no compactor/demotion wired — those need a project).
            use rig_core::memory::InMemoryConversationMemory;
            Arc::new(MbforgeManagedMemory::new(Arc::new(
                InMemoryConversationMemory::new(),
            )))
        }
    };
    let agent = build_mbforge_agent(&cfg, &spec, project_hook, managed_memory)?;
    // 4. 构造一个最小可用的 `LayeredContext`（系统 prompt 留空 —
    //    真正的 preamble 在 rig 端；这里只保留 L1 project / L3 history）
    let context = LayeredContext::new("", 20, 32_000);

    Ok(AgentSession {
        agent,
        context,
        memory,
        sidecar_url: sidecar_url.to_string(),
        audit,
        trajectory,
        audit_hook,
        trajectory_hook,
        project_root: project_root.map(PathBuf::from),
    })
}

/// 调对应的 rig factory 构造 `MbforgeAgent`。
///
/// 优先用调用方传入的 `project_hook`（项目级 audit + trajectory 复合钩子），
/// 保证 LLM 循环的审计/轨迹数据落到项目根的 `.mbforge/audit.jsonl`。
/// 失败 fallback 到临时 hook（保持向后兼容 + 测试场景）。
///
/// 历史：M4 引入 ConcreteHook，M5 命令层未提供按 project_root 构造真
/// ConcreteHook 的接口，临时用 `build_default_concrete_hook()` 兑底。
/// O-05（2026-06-06）：补上「接受传入 hook」接口，调用点有 project_root
/// 且 audit 创建成功时传项目级 hook。
fn build_mbforge_agent(
    cfg: &MbforgeProviderConfig,
    spec: &MbforgeAgentSpec,
    project_hook: Option<ConcreteHook>,
    memory: Arc<MbforgeManagedMemory>,
) -> Result<MbforgeAgent, String> {
    let hook = match project_hook {
        Some(h) => h,
        None => crate::core::agent::rig_adapter::build_default_concrete_hook()?,
    };
    match cfg.kind {
        MbforgeProviderKind::OpenAICompatible | MbforgeProviderKind::DeepSeek | MbforgeProviderKind::Ollama => {
            MbforgeAgent::from_openai_compatible(cfg, spec, vec![], hook, memory)
        }
        MbforgeProviderKind::Anthropic => {
            MbforgeAgent::from_anthropic(cfg, spec, vec![], hook, memory)
        }
    }
}
