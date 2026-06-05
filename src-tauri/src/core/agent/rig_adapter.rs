//! rig-core adapter — types that downstream code uses to talk to rig.
//!
//! This is the **only** module that imports `rig_core`. All agent construction
//! and tool wiring lives here, so a future framework swap touches one file.
//!
//! # Provider support
//!
//! Two providers are supported in the factory layer:
//!
//! 1. **OpenAI-compatible** — the MBForge sidecar (Python FastAPI on
//!    `localhost:18792`) speaks the OpenAI Chat Completions API. We use the
//!    rig `openai::CompletionsClient` with a custom `base_url`.
//! 2. **Anthropic** — direct access to the Anthropic Messages API. We use
//!    `rig_core::providers::anthropic::Client` and the `anthropic_betas`
//!    builder to enable beta features (extended thinking, prompt caching,
//!    1M context, etc.).
//!
//! # Stream / response types
//!
//! `MbforgeStreamItem` normalizes rig's `MultiTurnStreamItem` so the Tauri
//! layer doesn't have to know about rig's internals.

use std::pin::Pin;

use futures::Stream;

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
}

impl MbforgeProviderKind {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::OpenAICompatible => "openai_compatible",
            Self::Anthropic => "anthropic",
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

impl MbforgeProviderConfig {
    /// Build a config from the global `AppConfig` settings.
    pub fn from_app_config() -> Result<Self, String> {
        let app = crate::core::config::AppConfig::load();
        let kind = match app.llm.provider.as_str() {
            "anthropic" => MbforgeProviderKind::Anthropic,
            _ => MbforgeProviderKind::OpenAICompatible,
        };
        let base_url = match kind {
            MbforgeProviderKind::OpenAICompatible => {
                crate::core::config::constants::sidecar_url()
            }
            MbforgeProviderKind::Anthropic => {
                app.llm.base_url.clone().unwrap_or_default()
            }
        };
        Ok(Self {
            kind,
            base_url,
            api_key: app.llm.api_key.clone(),
            model: app.llm.model_name.clone(),
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

/// Type-erased rig agent. Wraps either an OpenAI-compatible or an Anthropic
/// rig agent and exposes the same `prompt` / `stream` API surface.
pub enum MbforgeAgent {
    OpenAI(rig_core::agent::Agent<rig_core::providers::openai::CompletionModel, ()>),
    Anthropic(rig_core::agent::Agent<rig_core::providers::anthropic::completion::CompletionModel, ()>),
}

impl MbforgeAgent {
    /// Identify the underlying provider.
    pub fn provider_kind(&self) -> MbforgeProviderKind {
        match self {
            Self::OpenAI(_) => MbforgeProviderKind::OpenAICompatible,
            Self::Anthropic(_) => MbforgeProviderKind::Anthropic,
        }
    }

    /// Single-shot prompt. Returns the final assistant text.
    pub async fn prompt(&self, input: &str) -> Result<String, String> {
        match self {
            Self::OpenAI(agent) => agent
                .prompt(input)
                .await
                .map(|r| r.to_string())
                .map_err(|e| format!("{e}")),
            Self::Anthropic(agent) => agent
                .prompt(input)
                .await
                .map(|r| r.to_string())
                .map_err(|e| format!("{e}")),
        }
    }

    /// Open a streaming prompt. The stream normalizes rig's internal
    /// `MultiTurnStreamItem` into the MBForge format.
    ///
    /// NOTE: the M2 release ships the `MbforgeStreamItem` types + the factories
    /// below. The full stream-mapping (turn-by-turn text deltas + tool calls)
    /// is implemented in M4 alongside the AgentBuilder rewiring. For now,
    /// `stream()` resolves to a one-shot prompt and emits a single `Final` item,
    /// which is enough for the M2 acceptance test (Tauri command layer does
    /// blocking `prompt()` calls; streaming is opt-in).
    pub fn stream(&self, input: &str) -> MbforgeStream {
        // M4: replace with `agent.stream_prompt(input).multi_turn(N).await` once the
        // async_stream / stream::unfold path is settled.
        match self.clone_prompt_then_collect(input) {
            Some(s) => s,
            None => Box::pin(futures::stream::empty()),
        }
    }

    fn clone_prompt_then_collect(&self, input: &str) -> Option<MbforgeStream> {
        // Placeholder: pre-collect the result. M4 will replace with real streaming.
        let input = input.to_owned();
        let fut = async move {
            match self_clone_prompt(self, &input).await {
                Ok(content) => Ok(MbforgeStreamItem::Final {
                    content,
                    prompt_tokens: 0,
                    completion_tokens: 0,
                }),
                Err(e) => Err(e),
            }
        };
        Some(Box::pin(futures::stream::once(fut)))
    }
}

async fn self_clone_prompt(agent: &MbforgeAgent, input: &str) -> Result<String, String> {
    agent.prompt(input).await
}

// ============================================================================
// Factories
// ============================================================================

impl MbforgeAgent {
    /// Build a fresh OpenAI-compatible agent from a provider config + spec.
    /// `extra_tools` are any pre-built `rig::tool::Tool` impls the caller
    /// wants to register (in production, this is where the 30+ native tools
    /// from `executor_rig.rs` + `arxiv_rig.rs` plug in).
    pub fn from_openai_compatible(
        cfg: &MbforgeProviderConfig,
        spec: &MbforgeAgentSpec,
        extra_tools: Vec<Box<dyn rig_core::tool::ToolDyn>>,
    ) -> Result<Self, String> {
        if cfg.kind != MbforgeProviderKind::OpenAICompatible {
            return Err(format!(
                "from_openai_compatible called with non-OpenAI config: {:?}",
                cfg.kind
            ));
        }
        let client = rig_core::providers::openai::Client::builder()
            .api_key(&cfg.api_key)
            .build()
            .map_err(|e| format!("openai client build failed: {e}"))?;
        // The MBForge sidecar speaks Chat Completions (not Responses), so we
        // route via CompletionsClient. For direct OpenAI usage the same client
        // works. The custom base_url comes from the config.
        let completions = if cfg.base_url.is_empty() {
            client
        } else {
            rig_core::providers::openai::CompletionsClient::builder()
                .api_key(&cfg.api_key)
                .base_url(&cfg.base_url)
                .build()
                .map_err(|e| format!("openai completions client build failed: {e}"))?
        };
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
        let builder = if extra_tools.is_empty() {
            builder
        } else {
            builder.tools(extra_tools)
        };
        Ok(Self::OpenAI(builder.build()))
    }

    /// Build a fresh Anthropic agent. Uses the rig Anthropic provider which
    /// supports beta features (extended thinking, prompt caching, 1M context).
    pub fn from_anthropic(
        cfg: &MbforgeProviderConfig,
        spec: &MbforgeAgentSpec,
        extra_tools: Vec<Box<dyn rig_core::tool::ToolDyn>>,
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
        let agent_builder = if extra_tools.is_empty() {
            agent_builder
        } else {
            agent_builder.tools(extra_tools)
        };
        Ok(Self::Anthropic(agent_builder.build()))
    }

    /// Convenience: pick the right factory based on `cfg.kind`.
    pub fn from_config(
        cfg: &MbforgeProviderConfig,
        spec: &MbforgeAgentSpec,
        extra_tools: Vec<Box<dyn rig_core::tool::ToolDyn>>,
    ) -> Result<Self, String> {
        match cfg.kind {
            MbforgeProviderKind::OpenAICompatible => {
                Self::from_openai_compatible(cfg, spec, extra_tools)
            }
            MbforgeProviderKind::Anthropic => {
                Self::from_anthropic(cfg, spec, extra_tools)
            }
        }
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
}
