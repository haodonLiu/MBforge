#![allow(dead_code)]
//! rig-core adapter — types that downstream code uses to talk to rig.
//!
//! This is the **only** module that imports `rig_core`. All agent construction
//! and tool wiring lives here, so a future framework swap touches one file.
//!
//! # Provider support
//!
//! Two providers are supported in the factory layer:
//!
//! 1. **OpenAI-compatible** — any service that speaks the OpenAI Chat
//!    Completions API (real OpenAI, OpenRouter, DeepSeek, a self-hosted
//!    llama.cpp server, etc.). We use the rig `openai::CompletionsClient`
//!    with `base_url` from `MBFORGE_LLM_BASE_URL`. The MBForge sidecar
//!    (FastAPI on `localhost:18792`) is **not** an OpenAI-compatible
//!    endpoint and is no longer used for LLM calls.
//! 2. **Anthropic** — direct access to the Anthropic Messages API. We use
//!    `rig_core::providers::anthropic::Client` and the `anthropic_betas`
//!    builder to enable beta features (extended thinking, prompt caching,
//!    1M context, etc.).
//!
//! Both providers read the **full** LLM config from environment variables
//! (`MBFORGE_LLM_PROVIDER` / `MBFORGE_LLM_BASE_URL` / `MBFORGE_LLM_API_KEY`
//! / `MBFORGE_LLM_MODEL`). The Settings UI displays these values read-only
//! and runs a connectivity test on app load; it cannot override them.
//!
//! # Stream / response types
//!
//! `MbforgeStreamItem` normalizes rig's `MultiTurnStreamItem` so the Tauri
//! layer doesn't have to know about rig's internals.

use std::pin::Pin;
use std::sync::Arc;

use futures::Stream;
use rig_core::client::CompletionClient;
use rig_core::completion::Prompt;
use rig_core::message::Message;

use crate::core::agent::managed_memory::MbforgeManagedMemory;
use crate::core::agent::session_id::SessionId;

// ============================================================================
// Stream types
// ============================================================================

/// Normalized streaming event the Tauri layer forwards to the frontend.
#[derive(Debug, Clone)]
pub enum MbforgeStreamItem {
    TextDelta(String),
    ToolCall {
        id: String,
        name: String,
        arguments: serde_json::Value,
    },
    ToolResult {
        id: String,
        name: String,
        result: String,
    },
    Final {
        content: String,
        prompt_tokens: u64,
        completion_tokens: u64,
    },
}

pub type MbforgeStream = Pin<Box<dyn Stream<Item = Result<MbforgeStreamItem, String>> + Send>>;

// ============================================================================
// Provider + spec config
// ============================================================================

/// Which LLM provider to use.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MbforgeProviderKind {
    /// OpenAI-compatible (sidecar, real OpenAI, OpenRouter, etc.)
    OpenAICompatible,
    /// Anthropic Messages API (Claude)
    Anthropic,
    /// DeepSeek (OpenAI-compatible at api.deepseek.com/v1)
    DeepSeek,
    /// Ollama 本地推理 (OpenAI-compatible at localhost:11434/v1)
    Ollama,
}

impl MbforgeProviderKind {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::OpenAICompatible => "openai_compatible",
            Self::Anthropic => "anthropic",
            Self::DeepSeek => "deepseek",
            Self::Ollama => "ollama",
        }
    }
}

/// Configuration for the LLM provider backing an agent.
#[derive(Debug, Clone)]
pub struct MbforgeProviderConfig {
    pub kind: MbforgeProviderKind,
    /// Base URL. For sidecar: `http://127.0.0.1:18792/v1`. For Anthropic: leave empty
    /// (uses `api.anthropic.com`) or set a custom proxy.
    pub base_url: String,
    /// API key for the provider.
    pub api_key: String,
    /// Model identifier (e.g. "gpt-4o-mini", "claude-sonnet-4-5", "claude-opus-4-1").
    pub model: String,
    /// HTTP request timeout in seconds.
    pub timeout_secs: u64,
    /// Anthropic-specific: beta feature flags. Empty for production-stable features.
    /// Common values: "prompt-caching-2024-07-31", "extended-thinking-2025-01-01",
    /// "context-1m-2025-08-07" (for 1M context models).
    pub anthropic_betas: Vec<String>,
}

/// Read the first non-empty value among the given env-var names.
/// Returns `None` if none of the names is set or all are blank.
#[allow(dead_code)]
fn first_nonempty(names: &[&str]) -> Option<String> {
    names
        .iter()
        .find_map(|n| std::env::var(n).ok().filter(|s| !s.trim().is_empty()))
}

impl MbforgeProviderConfig {
    /// Build a config from environment variables (`.env` injected at startup
    /// by `main::load_dotenv()`).
    ///
    /// Resolution — **env-only, no fallback**. The project-root `.env` is the
    /// single source of truth; if any required var is missing, this function
    /// returns an error and the caller surfaces it. There is no default
    /// endpoint, no `config.json` fallback, and no graceful "not configured"
    /// status — the LLM simply cannot be used without env configuration.
    ///
    /// - Provider kind: `MBFORGE_LLM_PROVIDER` (`anthropic` → Anthropic,
    ///   anything else → OpenAI-compatible).
    /// - Base URL / API key / model: `MBFORGE_LLM_BASE_URL` /
    ///   `MBFORGE_LLM_API_KEY` / `MBFORGE_LLM_MODEL` (all required).
    ///
    /// The Settings UI cannot override these — they are the single source of
    /// truth, in line with the project convention (`MBFORGE_SIDECAR_URL`,
    /// `MBFORGE_MODEL_CACHE_DIR`, etc.).
    pub fn from_app_config() -> Result<Self, String> {
        let env_provider = std::env::var("MBFORGE_LLM_PROVIDER")
            .ok()
            .filter(|s| !s.trim().is_empty());
        let kind = match env_provider.as_deref() {
            Some("anthropic") => MbforgeProviderKind::Anthropic,
            Some("deepseek") => MbforgeProviderKind::DeepSeek,
            Some("ollama") => MbforgeProviderKind::Ollama,
            _ => MbforgeProviderKind::OpenAICompatible,
        };
        let env = |k: &str| std::env::var(k).ok().filter(|s| !s.trim().is_empty());
        let base_url = env("MBFORGE_LLM_BASE_URL").unwrap_or_default();
        let api_key = env("MBFORGE_LLM_API_KEY").unwrap_or_default();
        let model = env("MBFORGE_LLM_MODEL").unwrap_or_default();
        if base_url.trim().is_empty() {
            return Err(format!(
                "LLM base_url is not configured. Set `MBFORGE_LLM_BASE_URL` in the project-root .env \
                 to an OpenAI-compatible endpoint (e.g. https://api.openai.com/v1, \
                 https://openrouter.ai/api/v1, https://api.deepseek.com/v1, or a self-hosted \
                 llama.cpp server). The MBForge sidecar on :18792 is *not* an OpenAI-compatible \
                 endpoint and must not be used here."
            ));
        }
        if api_key.trim().is_empty() {
            return Err(format!(
                "LLM api_key is not configured. Set `MBFORGE_LLM_API_KEY` in the project-root .env."
            ));
        }
        if model.trim().is_empty() {
            return Err(format!(
                "LLM model is not configured. Set `MBFORGE_LLM_MODEL` in the project-root .env."
            ));
        }
        Ok(Self {
            kind,
            base_url,
            api_key,
            model,
            timeout_secs: 120,
            anthropic_betas: Vec::new(),
        })
    }

    /// Test-only config (no real network calls).
    pub fn for_tests() -> Self {
        Self {
            kind: MbforgeProviderKind::OpenAICompatible,
            base_url: "http://127.0.0.1:0".into(),
            api_key: "test-key".into(),
            model: "test-model".into(),
            timeout_secs: 5,
            anthropic_betas: Vec::new(),
        }
    }

    /// Test config for Anthropic.
    pub fn for_tests_anthropic() -> Self {
        Self {
            kind: MbforgeProviderKind::Anthropic,
            base_url: String::new(),
            api_key: "test-anthropic-key".into(),
            model: "claude-sonnet-4-5".into(),
            timeout_secs: 5,
            anthropic_betas: vec!["extended-thinking-2025-01-01".into()],
        }
    }
}

/// Lightweight "system prompt + tool whitelist + max iterations" spec for an agent.
#[derive(Debug, Clone)]
pub struct MbforgeAgentSpec {
    pub name: String,
    pub system_prompt: String,
    pub max_turns: usize,
    pub max_tokens: Option<u64>,
    pub temperature: Option<f64>,
}

impl MbforgeAgentSpec {
    pub fn general() -> Self {
        Self {
            name: "general_agent".into(),
            system_prompt: String::new(),
            max_turns: 5,
            max_tokens: None,
            temperature: None,
        }
    }
    pub fn literature() -> Self {
        Self {
            name: "literature_agent".into(),
            // Migrated from `specialist_agent::LITERATURE_AGENT_SYSTEM_PROMPT` in M5.
            // M6 will delete the legacy constant.
            system_prompt: String::from(
                "你是文献处理 agent — **最上游**的角色。\n\
                 \n\
                 # 输入\n\
                 - PDF 抽取结果（结构化 JSON）：compounds / activities / key_findings\n\
                 - 不要再做抽取\n\
                 \n\
                 # 工具（4 个）\n\
                 - `lit_mol_register` — 注册分子到项目 molecule store\n\
                 - `lit_note_add` — 添加结构化笔记\n\
                 - `lit_label_apply` — 给已注册分子打标签\n\
                 - `lit_chem_validate` — 校验 SMILES 合法性\n\
                 \n\
                 # 输出\n\
                 - 自然语言总结：注册了哪些分子 / 哪些需要人工审核 / 关键发现\n\
                 - 不需要再调下游工具\n\
                 \n\
                 # 规则\n\
                 1. 一次 process() 调 = 一次完整处理，不要跨调用维持上下文\n\
                 2. 不在工具集里：不要试图调 KB search / file read / literature search\n\
                 3. 遇到 SMILES 合法性问题：先调 `lit_chem_validate`，失败则不调 `lit_mol_register`\n\
                 4. 批量注册：使用多次 `lit_mol_register` 调用，一次注册一个分子\n\
                 5. 置信度诚实：description 不清晰就改用 `lit_note_add` 留待人工审核\n",
            ),
            max_turns: 8,
            max_tokens: None,
            temperature: None,
        }
    }
}

// ============================================================================
// MbforgeAgent — factory + provider-agnostic surface
// ============================================================================

// ============================================================================
// ConcreteHook — composite rig PromptHook wiring audit + trajectory
// ============================================================================

/// `PromptHook` that fans every rig event out to both the audit log and the
/// trajectory tracker. Required because the rig 0.38.1 `Agent<M, P>` generic
/// is invariant in `P` — passing the unit hook (`()`) would lose both
/// observability sinks. Keeping them in a single struct means each rig agent
/// owns exactly one concrete hook and we don't need trait objects.
///
/// `PromptHook` (rig 0.38.1) requires `Clone + WasmCompatSend + WasmCompatSync`,
/// so `ConcreteHook` derives `Clone`. The inner `AuditLogHook` and
/// `TrajectoryHook` each wrap their state in `Arc<…>` and implement `Clone`
/// manually, so cloning `ConcreteHook` is cheap (just bumps the `Arc` refs).
#[derive(Clone)]
pub struct ConcreteHook {
    pub audit: crate::core::agent::rig_hooks::AuditLogHook,
    pub trajectory: crate::core::agent::rig_hooks::TrajectoryHook,
}

impl<M> rig_core::agent::PromptHook<M> for ConcreteHook
where
    M: rig_core::completion::CompletionModel + 'static,
{
    /// Record an `llm_call` audit entry. The trajectory hook has no override
    /// for this event (it only tracks tool calls), so the default `cont()`
    /// handles that side. We bypass `AuditLogHook::record_llm_call` (a
    /// private method on the inner hook) and call the public `AuditLog`
    /// directly. This keeps the trait-object-free call graph and avoids
    /// needing `CompletionResponse: Clone` (only `Usage` is extracted, and
    /// `Usage` is `Copy`).
    fn on_completion_response(
        &self,
        _prompt: &Message,
        response: &rig_core::completion::CompletionResponse<M::Response>,
    ) -> impl std::future::Future<Output = rig_core::agent::HookAction>
    + rig_core::wasm_compat::WasmCompatSend {
        let audit_log = self.audit.audit.clone();
        let trace_id = self.audit.trace_id.clone();
        let usage = response.usage;
        async move {
            let _ = audit_log.append_llm_call(
                &trace_id,
                None,
                "rig-agent",
                usage.input_tokens,
                usage.output_tokens,
                0,
            );
            rig_core::agent::HookAction::cont()
        }
    }

    /// Forward to both inner sinks. The audit hook records a `tool_call`
    /// entry; the trajectory hook records a step. We replicate the inner
    /// hooks' formatting (best-effort JSON parse of args, append+fsync) so we
    /// don't need to expose their private helpers.
    fn on_tool_result(
        &self,
        tool_name: &str,
        _tool_call_id: Option<String>,
        _internal_call_id: &str,
        args: &str,
        result: &str,
    ) -> impl std::future::Future<Output = rig_core::agent::HookAction>
    + rig_core::wasm_compat::WasmCompatSend {
        let audit_log = self.audit.audit.clone();
        let trace_id_audit = self.audit.trace_id.clone();
        let trajectory_tracker = self.trajectory.tracker.clone();
        let tool_name = tool_name.to_owned();
        let args = args.to_owned();
        let result = result.to_owned();
        async move {
            // Audit sink: same shape as `AuditLogHook::record_tool_call`.
            let args_value: serde_json::Value = serde_json::from_str(&args)
                .unwrap_or(serde_json::Value::String(args.clone()));
            let _ = audit_log.append_tool_call(
                &trace_id_audit,
                None,
                &tool_name,
                &args_value,
                0,
            );
            // Trajectory sink: same shape as `TrajectoryHook::record`.
            if let Ok(mut guard) = trajectory_tracker.lock() {
                guard.record_tool(&tool_name, &args_value, &result);
            }
            rig_core::agent::HookAction::cont()
        }
    }
}

/// Type-erased rig agent. Wraps either an OpenAI-compatible or an Anthropic
/// rig agent and exposes the same `prompt` / `stream` API surface.
///
/// Each arm holds the underlying rig agent *and* an
/// `Arc<MbforgeManagedMemory>` (the rig `ConversationMemory` impl
/// that owns the SQLite backend + compactor + demotion hook). The
/// memory is wired into the rig builder at construction time via
/// `.memory(...)`; the `prompt` and `stream` methods pass
/// `&SessionId` to rig's per-request `PromptRequest::conversation(...)`
/// so rig loads/appends the matching conversation thread.
#[derive(Clone)]
pub enum MbforgeAgent {
    OpenAI((
        rig_core::agent::Agent<rig_core::providers::openai::CompletionModel, ConcreteHook>,
        Arc<MbforgeManagedMemory>,
    )),
    Anthropic((
        rig_core::agent::Agent<rig_core::providers::anthropic::completion::CompletionModel, ConcreteHook>,
        Arc<MbforgeManagedMemory>,
    )),
}

impl MbforgeAgent {
    /// Identify the underlying provider.
    pub fn provider_kind(&self) -> MbforgeProviderKind {
        match self {
            Self::OpenAI(_) => MbforgeProviderKind::OpenAICompatible,
            Self::Anthropic(_) => MbforgeProviderKind::Anthropic,
        }
    }

    /// Borrow the memory backend (the rig `ConversationMemory` impl
    /// that owns the SQLite store + compactor + demotion hook).
    pub fn memory(&self) -> Arc<MbforgeManagedMemory> {
        match self {
            Self::OpenAI((_, m)) | Self::Anthropic((_, m)) => Arc::clone(m),
        }
    }

    /// Single-shot prompt bound to `cid`. Rig loads the conversation
    /// history for `cid` from the configured memory backend before the
    /// LLM call and appends `[user, assistant]` after a successful
    /// turn. The final assistant text is returned.
    pub async fn prompt(&self, cid: &SessionId, input: &str) -> Result<String, String> {
        match self {
            Self::OpenAI((agent, _)) => agent
                .prompt(input)
                .conversation(cid.as_str())
                .await
                .map(|r| r.to_string())
                .map_err(|e| format!("{e}")),
            Self::Anthropic((agent, _)) => agent
                .prompt(input)
                .conversation(cid.as_str())
                .await
                .map(|r| r.to_string())
                .map_err(|e| format!("{e}")),
        }
    }

    /// Open a streaming prompt bound to `cid`. The stream normalizes
    /// rig's internal `MultiTurnStreamItem` into the MBForge format
    /// via `map_rig_stream`.
    pub fn stream(&self, cid: &SessionId, input: &str) -> MbforgeStream {
        let input = input.to_owned();
        let cid = cid.as_str().to_owned();
        let max_turns = self.default_max_turns();
        match self {
            Self::OpenAI((agent, _mem)) => {
                let agent = agent.clone();
                map_rig_stream(async move {
                    use rig_core::streaming::StreamingPrompt;
                    agent
                        .stream_prompt(input)
                        .conversation(cid.as_str())
                        .multi_turn(max_turns)
                        .await
                })
            }
            Self::Anthropic((agent, _mem)) => {
                let agent = agent.clone();
                map_rig_stream(async move {
                    use rig_core::streaming::StreamingPrompt;
                    agent
                        .stream_prompt(input)
                        .conversation(cid.as_str())
                        .multi_turn(max_turns)
                        .await
                })
            }
        }
    }

    /// Read the persisted history for `cid` as MBForge `Message`s.
    /// Used by `agent_get_history` (replaces the dead
    /// `LayeredContext::get_history_messages`).
    pub async fn history(
        &self,
        cid: &SessionId,
    ) -> Result<Vec<crate::core::agent::context::Message>, String> {
        let memory = self.memory();
        let items = memory
            .list_for_session(cid.as_str())
            .map_err(|e| format!("list_for_session: {e}"))?;
        Ok(items
            .into_iter()
            .map(|item| {
                let role = if item.is_summary { "system" } else { item.role.as_str() };
                match role {
                    "system" => crate::core::agent::context::Message::system(&item.content),
                    "assistant" => crate::core::agent::context::Message::assistant(&item.content),
                    _ => crate::core::agent::context::Message::user(&item.content),
                }
            })
            .collect())
    }

    /// Pull the `default_max_turns` off whichever inner agent we hold. Used
    /// by `stream()` to bound the agent loop the same way the spec did.
    fn default_max_turns(&self) -> usize {
        match self {
            Self::OpenAI((agent, _)) => agent.default_max_turns,
            Self::Anthropic((agent, _)) => agent.default_max_turns,
        }
        .unwrap_or(5)
    }
}

// ============================================================================
// Factories
// ============================================================================

impl MbforgeAgent {
    /// Build a fresh OpenAI-compatible agent from a provider config + spec.
    /// `extra_tools` are any pre-built `rig::tool::Tool` impls the caller
    /// wants to register (in production, this is where the 30+ native tools
    /// from `executor_rig.rs` + `arxiv_rig.rs` plug in). `hook` is the
    /// concrete observability hook (audit + trajectory) that rig fires
    /// during the prompt loop. The agent's `P` generic parameter is fixed
    /// to `ConcreteHook`; the unit hook `()` is no longer supported.
    pub fn from_openai_compatible(
        cfg: &MbforgeProviderConfig,
        spec: &MbforgeAgentSpec,
        extra_tools: Vec<Box<dyn rig_core::tool::ToolDyn>>,
        hook: ConcreteHook,
        memory: Arc<MbforgeManagedMemory>,
    ) -> Result<Self, String> {
        if cfg.kind != MbforgeProviderKind::OpenAICompatible {
            return Err(format!(
                "from_openai_compatible called with non-OpenAI config: {:?}",
                cfg.kind
            ));
        }
        // The MBForge sidecar speaks the OpenAI Chat Completions protocol on
        // a custom base_url. We always go through `CompletionsClient` so the
        // return type is a single `Client<OpenAICompletionsExt>`, which makes
        // the `Self::OpenAI` arm of the enum carry a homogeneous model type.
        let mut cb = rig_core::providers::openai::CompletionsClient::builder()
            .api_key(&cfg.api_key);
        if !cfg.base_url.is_empty() {
            cb = cb.base_url(&cfg.base_url);
        }
        let completions = cb
            .build()
            .map_err(|e| format!("openai completions client build failed: {e}"))?;
        let mut builder = completions
            .agent(&cfg.model)
            .preamble(&spec.system_prompt)
            .default_max_turns(spec.max_turns);
        if let Some(t) = spec.temperature {
            builder = builder.temperature(t);
        }
        if let Some(n) = spec.max_tokens {
            builder = builder.max_tokens(n);
        }
        // `.tools()` consumes the builder and changes the `ToolState` type
        // parameter, so we must call it unconditionally to keep the
        // if/else arms homogeneous. An empty vec is a no-op at runtime.
        // `.hook()` similarly consumes the builder to flip the `P` generic
        // parameter; the order (tools → hook → build) is irrelevant as long
        // as both run before `.build()`.
        let builder = builder
            .tools(extra_tools)
            .hook(hook)
            .memory(Arc::clone(&memory))
            .conversation_id("__default__");
        Ok(Self::OpenAI((builder.build(), memory)))
    }

    /// Build a fresh Anthropic agent. Uses the rig Anthropic provider which
    /// supports beta features (extended thinking, prompt caching, 1M context).
    pub fn from_anthropic(
        cfg: &MbforgeProviderConfig,
        spec: &MbforgeAgentSpec,
        extra_tools: Vec<Box<dyn rig_core::tool::ToolDyn>>,
        hook: ConcreteHook,
        memory: Arc<MbforgeManagedMemory>,
    ) -> Result<Self, String> {
        if cfg.kind != MbforgeProviderKind::Anthropic {
            return Err(format!(
                "from_anthropic called with non-Anthropic config: {:?}",
                cfg.kind
            ));
        }
        let mut builder = rig_core::providers::anthropic::Client::builder()
            .api_key(&cfg.api_key);
        if !cfg.base_url.is_empty() {
            builder = builder.base_url(&cfg.base_url);
        }
        if !cfg.anthropic_betas.is_empty() {
            let betas: Vec<&str> = cfg.anthropic_betas.iter().map(|s| s.as_str()).collect();
            builder = builder.anthropic_betas(&betas);
        }
        let client = builder
            .build()
            .map_err(|e| format!("anthropic client build failed: {e}"))?;
        let mut agent_builder = client
            .agent(&cfg.model)
            .preamble(&spec.system_prompt)
            .default_max_turns(spec.max_turns);
        if let Some(t) = spec.temperature {
            agent_builder = agent_builder.temperature(t);
        }
        if let Some(n) = spec.max_tokens {
            agent_builder = agent_builder.max_tokens(n);
        }
        // `.tools()` consumes the builder and changes the `ToolState` type
        // parameter, so we must call it unconditionally to keep the
        // if/else arms homogeneous. An empty vec is a no-op at runtime.
        // `.hook()` flips the `P` generic; ordering with `.tools()` does not
        // matter as long as both fire before `.build()`.
        let agent_builder = agent_builder
            .tools(extra_tools)
            .hook(hook)
            .memory(Arc::clone(&memory))
            .conversation_id("__default__");
        Ok(Self::Anthropic((agent_builder.build(), memory)))
    }

    /// Convenience: pick the right factory based on `cfg.kind`. The
    /// observability hook is built internally from a fresh `tempfile::tempdir`
    /// — call sites that need a real audit log + trajectory file should use
    /// `from_openai_compatible_with_all_tools` / `from_anthropic_with_all_tools`
    /// directly and pass a `ConcreteHook` constructed against a real
    /// `project_root`.
    pub fn from_config(
        cfg: &MbforgeProviderConfig,
        spec: &MbforgeAgentSpec,
        extra_tools: Vec<Box<dyn rig_core::tool::ToolDyn>>,
        memory: Arc<MbforgeManagedMemory>,
    ) -> Result<Self, String> {
        let hook = build_default_concrete_hook()?;
        match cfg.kind {
            MbforgeProviderKind::OpenAICompatible => {
                Self::from_openai_compatible(cfg, spec, extra_tools, hook, memory)
            }
            MbforgeProviderKind::Anthropic => {
                Self::from_anthropic(cfg, spec, extra_tools, hook, memory)
            }
        }
    }

    /// Convenience: build an OpenAI-compatible agent with all 25 rig-native
    /// tools wired up (16 executor tools + 9 arxiv tools). `project_root`
    /// is the MBForge project directory the tools' `executor_rig::*` files
    /// will read from. `hook` carries the audit + trajectory sinks; pass a
    /// hook built against the same `project_root` for the audit entries to
    /// land in `<project_root>/.mbforge/audit.jsonl`. `memory` is the
    /// rig `ConversationMemory` backend; pass one built from
    /// `SqliteConversationMemory::open(project_root)` for persistence.
    pub fn from_openai_compatible_with_all_tools(
        cfg: &MbforgeProviderConfig,
        spec: &MbforgeAgentSpec,
        project_root: &str,
        hook: ConcreteHook,
        memory: Arc<MbforgeManagedMemory>,
    ) -> Result<Self, String> {
        let tools = assemble_rig_tool_vec(project_root);
        Self::from_openai_compatible(cfg, spec, tools, hook, memory)
    }

    /// Anthropic counterpart of `from_openai_compatible_with_all_tools`.
    /// Same 25-tool set; differs only in the provider client.
    pub fn from_anthropic_with_all_tools(
        cfg: &MbforgeProviderConfig,
        spec: &MbforgeAgentSpec,
        project_root: &str,
        hook: ConcreteHook,
        memory: Arc<MbforgeManagedMemory>,
    ) -> Result<Self, String> {
        let tools = assemble_rig_tool_vec(project_root);
        Self::from_anthropic(cfg, spec, tools, hook, memory)
    }
}

// ============================================================================
// Helpers (tool assembly + default hook construction)
// ============================================================================

use crate::core::agent::arxiv_rig::{
    ArxivBrief, ArxivMetadata, ArxivPreview, ArxivRaw, ArxivSearch, ArxivSection, ArxivTrending,
    PmcJson, PmcMetadata,
};
use crate::core::agent::executor_rig::{
    CheckMarkushTool, FindDocumentsTool, GetDocumentPagesTool, GetDocumentStructureTool,
    GetDocumentSummaryTool, GetProjectInfoTool, GlobSearchTool, GrepSearchTool, ListDocumentsTool,
    ListFilesTool, MoleculeAnalysisTool, ReadDocumentAbstractTool, ReadDocumentDetailTool,
    ReadDocumentOverviewTool, ReadFileTool, SearchKbTool,
};
use crate::core::agent::observability::AuditLog;
use crate::core::agent::rig_hooks::{AuditLogHook, TrajectoryHook};
use crate::core::agent::trajectory::TrajectoryTracker;

/// Phase 4 宏化：把所有 25 个 rig 工具的构造集中到一个宏里。
///
/// 调用：`assemble_rig_tool_vec!(project_root)` 生成 `Vec<Box<dyn ToolDyn>>`。
/// 新增工具：直接修改宏体里的 `tools.push(...)` 列表。
macro_rules! assemble_rig_tool_vec {
    ($project_root:expr) => {{
        let mut tools: Vec<Box<dyn rig_core::tool::ToolDyn>> = Vec::with_capacity(25);
        // 16 executor tools (take project_root).
        tools.push(Box::new(GrepSearchTool::new($project_root)));
        tools.push(Box::new(ListFilesTool::new($project_root)));
        tools.push(Box::new(ReadFileTool::new($project_root)));
        tools.push(Box::new(GetProjectInfoTool::new($project_root)));
        tools.push(Box::new(GlobSearchTool::new($project_root)));
        tools.push(Box::new(SearchKbTool::new($project_root)));
        tools.push(Box::new(GetDocumentStructureTool::new($project_root)));
        tools.push(Box::new(GetDocumentPagesTool::new($project_root)));
        tools.push(Box::new(CheckMarkushTool::new()));
        tools.push(Box::new(MoleculeAnalysisTool::new($project_root)));
        tools.push(Box::new(ReadDocumentAbstractTool::new($project_root)));
        tools.push(Box::new(ReadDocumentOverviewTool::new($project_root)));
        tools.push(Box::new(ListDocumentsTool::new($project_root)));
        tools.push(Box::new(GetDocumentSummaryTool::new($project_root)));
        tools.push(Box::new(ReadDocumentDetailTool::new($project_root)));
        tools.push(Box::new(FindDocumentsTool::new($project_root)));
        // 9 arxiv tools (unit structs).
        tools.push(Box::new(ArxivMetadata));
        tools.push(Box::new(ArxivBrief));
        tools.push(Box::new(ArxivPreview));
        tools.push(Box::new(ArxivRaw));
        tools.push(Box::new(ArxivSection));
        tools.push(Box::new(ArxivSearch));
        tools.push(Box::new(ArxivTrending));
        tools.push(Box::new(PmcMetadata));
        tools.push(Box::new(PmcJson));
        // ThinkTool：Anthropic 推荐的"思考工具"，让 agent 在复杂步骤前显式写下推理
        tools.push(Box::new(rig_core::tools::ThinkTool));
        tools
    }};
}

/// Assemble the 25 rig-native tools the MBForge agent stack expects:
/// 16 from `executor_rig` (file system, KB, document, molecule) and 9
/// from `arxiv_rig` (arxiv + PMC literature). They are boxed in declaration
/// order so tool names sort the same way across runs.
///
/// Phase 4 改造：函数体仅一行宏调用；具体工具列表见 `assemble_rig_tool_vec!` 宏。
pub fn assemble_rig_tool_vec(project_root: &str) -> Vec<Box<dyn rig_core::tool::ToolDyn>> {
    assemble_rig_tool_vec!(project_root)
}

/// Build a `ConcreteHook` from a fresh `tempfile::tempdir()`. Used by
/// `from_config` which has no `project_root` argument and by tests that
/// need a hook without setting up a real audit directory.
///
/// Returns an error only if the tempdir / audit-log file cannot be created,
/// which in practice means a permission / disk issue at the OS layer.
pub(crate) fn build_default_concrete_hook() -> Result<ConcreteHook, String> {
    let dir = tempfile::tempdir().map_err(|e| format!("tempfile::tempdir failed: {e}"))?;
    let audit = AuditLog::new(dir.path())
        .map_err(|e| format!("AuditLog::new({}) failed: {e}", dir.path().display()))?;
    let audit_hook = AuditLogHook::new(Arc::new(audit));
    let trajectory = TrajectoryTracker::new(dir.path());
    let trajectory_hook = TrajectoryHook::new(trajectory);
    Ok(ConcreteHook {
        audit: audit_hook,
        trajectory: trajectory_hook,
    })
}


// ============================================================================
// Stream mapping (rig MultiTurnStreamItem -> MbforgeStreamItem)
// ============================================================================

use rig_core::agent::{MultiTurnStreamItem, StreamingError, StreamingResult};
use rig_core::completion::message::ToolResultContent;
use rig_core::streaming::{StreamedAssistantContent, StreamedUserContent};

/// Take the future that rig's `stream_prompt().multi_turn(N).await` returns
/// and re-shape it into a `MbforgeStream`. The future resolves to a
/// `StreamingResult<R>` (a `Pin<Box<dyn Stream<…> + Send>>`); we drive it
/// with `futures::stream::unfold` so each rig item becomes 0–1
/// `MbforgeStreamItem`s.
///
/// This avoids pulling in `async-stream` (a transitive rig-core dep that
/// isn't a direct Cargo dep) while still giving the call site an
/// ordinary `Stream` to consume.
pub(crate) fn map_rig_stream<R, F>(fut: F) -> MbforgeStream
where
    F: std::future::Future<Output = StreamingResult<R>> + Send + 'static,
    R: Send + 'static,
{
    use futures::stream::StreamExt;
    // `stream::once` yields the inner stream once, then we `flat_map` to
    // unfold it into a stream of `MbforgeStreamItem`s.
    let outer = futures::stream::once(fut).flat_map(|inner: StreamingResult<R>| {
        futures::stream::unfold(inner, move |mut inner| async move {
            match inner.next().await {
                Some(Ok(item)) => Some((map_multi_turn_item(item), inner)),
                Some(Err(e)) => Some((Err(format_streaming_error(&e)), inner)),
                None => None,
            }
        })
    });
    Box::pin(outer)
}

fn format_streaming_error(e: &StreamingError) -> String {
    format!("{e}")
}
/// Convert one rig multi-turn stream item to a `MbforgeStreamItem`. Returns
/// `Ok(MbforgeStreamItem::TextDelta(String::new()))` (a no-op delta) for items
/// we don't surface to the frontend; callers can filter these out if needed.
fn map_multi_turn_item<R>(item: MultiTurnStreamItem<R>) -> Result<MbforgeStreamItem, String> {
    match item {
        MultiTurnStreamItem::StreamAssistantItem(content) => Ok(match content {
            StreamedAssistantContent::Text(text) => MbforgeStreamItem::TextDelta(text.text),
            StreamedAssistantContent::ToolCall { tool_call, .. } => {
                MbforgeStreamItem::ToolCall {
                    id: tool_call.id,
                    name: tool_call.function.name,
                    arguments: tool_call.function.arguments,
                }
            }
            // Deltas, reasoning, and the embedded `Final(R)` are dropped from
            // the frontend stream; the hook still sees them and the terminal
            // `FinalResponse` carries the aggregated text + usage.
            StreamedAssistantContent::ToolCallDelta { .. }
            | StreamedAssistantContent::Reasoning(_)
            | StreamedAssistantContent::ReasoningDelta { .. }
            | StreamedAssistantContent::Final(_) => MbforgeStreamItem::TextDelta(String::new()),
        }),
        MultiTurnStreamItem::StreamUserItem(StreamedUserContent::ToolResult {
            tool_result,
            internal_call_id,
        }) => {
            // Concatenate the text fragments of the tool result content; the
            // MBForge frontend only needs the rendered string.
            let result = tool_result
                .content
                .into_iter()
                .map(|c| match c {
                    ToolResultContent::Text(t) => t.text,
                    ToolResultContent::Image(_) => String::new(),
                })
                .collect::<Vec<_>>()
                .join("");
            Ok(MbforgeStreamItem::ToolResult {
                id: tool_result.id,
                name: internal_call_id,
                result,
            })
        }
        MultiTurnStreamItem::CompletionCall(_) => {
            // Per-completion usage events are dropped from the frontend
            // stream; the aggregated usage comes through on `FinalResponse`.
            Ok(MbforgeStreamItem::TextDelta(String::new()))
        }
        MultiTurnStreamItem::FinalResponse(final_response) => {
            let usage = final_response.usage();
            Ok(MbforgeStreamItem::Final {
                content: final_response.response().to_string(),
                prompt_tokens: usage.input_tokens,
                completion_tokens: usage.output_tokens,
            })
        }
        // `MultiTurnStreamItem` is `#[non_exhaustive]`. Future rig versions
        // may add new variants; treat them as no-op deltas so we don't break.
        _ => Ok(MbforgeStreamItem::TextDelta(String::new())),
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mbforge_provider_config_for_tests() {
        let cfg = MbforgeProviderConfig::for_tests();
        assert_eq!(cfg.kind, MbforgeProviderKind::OpenAICompatible);
        assert!(cfg.base_url.contains("127.0.0.1"));
        assert_eq!(cfg.timeout_secs, 5);
    }

    #[test]
    fn test_mbforge_provider_config_anthropic() {
        let cfg = MbforgeProviderConfig::for_tests_anthropic();
        assert_eq!(cfg.kind, MbforgeProviderKind::Anthropic);
        assert_eq!(cfg.model, "claude-sonnet-4-5");
        assert!(cfg.anthropic_betas.contains(&"extended-thinking-2025-01-01".to_string()));
    }

    #[test]
    fn test_mbforge_agent_spec_general() {
        let spec = MbforgeAgentSpec::general();
        assert_eq!(spec.name, "general_agent");
        assert_eq!(spec.max_turns, 5);
    }

    #[test]
    fn test_mbforge_agent_spec_literature() {
        let spec = MbforgeAgentSpec::literature();
        assert_eq!(spec.name, "literature_agent");
        assert_eq!(spec.max_turns, 8);
    }

    #[test]
    fn test_mbforge_provider_kind_as_str() {
        assert_eq!(MbforgeProviderKind::OpenAICompatible.as_str(), "openai_compatible");
        assert_eq!(MbforgeProviderKind::Anthropic.as_str(), "anthropic");
    }

    /// Verify the `ConcreteHook` composes the inner audit + trajectory
    /// hooks correctly and exposes the trait's default methods. We pick
    /// `rig_core::providers::openai::CompletionModel` as the `M` parameter
    /// for `PromptHook<M>` because it's already in scope as a re-export
    /// of the actual `GenericCompletionModel<OpenAICompletionsExt, H>`
    /// — the test never instantiates it, just needs a type that
    /// implements `CompletionModel` so the trait method is callable.
    #[tokio::test(flavor = "current_thread")]
    async fn test_concrete_hook_default_methods() {
        use rig_core::agent::PromptHook;
        type M = rig_core::providers::openai::CompletionModel;
        let hook = build_default_concrete_hook().expect("default hook builds");
        // The struct composes the two inner hooks (cheap `Clone` via `Arc`).
        let _clone = hook.clone();
        // Default `on_completion_call` (we didn't override it) returns `cont`.
        let action = <ConcreteHook as PromptHook<M>>::on_completion_call(
            &hook,
            &Message::user("test"),
            &[],
        )
        .await;
        assert!(
            matches!(action, rig_core::agent::HookAction::Continue),
            "default on_completion_call should be HookAction::Continue"
        );
        // Sanity-check that the inner hooks survived the construction.
        assert!(!hook.audit.trace_id.is_empty());
        assert!(!hook.trajectory.trace_id.is_empty());
    }

    /// Verify the `from_openai_compatible` factory rejects an Anthropic
    /// config. This guards the runtime check in the factory; if the check
    /// ever regresses the test fails immediately.
    #[test]
    fn test_from_openai_compatible_validates_kind() {
        let cfg = MbforgeProviderConfig::for_tests_anthropic();
        let spec = MbforgeAgentSpec::general();
        let hook = build_default_concrete_hook().expect("default hook builds");
        // The factory's kind check fires before any memory access, so a
        // bare in-memory backend is enough to drive this test.
        use rig_core::memory::InMemoryConversationMemory;
        let memory = std::sync::Arc::new(
            crate::core::agent::managed_memory::MbforgeManagedMemory::new(
                std::sync::Arc::new(InMemoryConversationMemory::new()),
            ),
        );
        let res = MbforgeAgent::from_openai_compatible(&cfg, &spec, Vec::new(), hook, memory);
        match res {
            Err(msg) => assert!(
                msg.contains("from_openai_compatible called with non-OpenAI"),
                "unexpected error message: {msg}"
            ),
            Ok(_) => panic!("expected Err for non-OpenAI config, got Ok"),
        }
    }
}