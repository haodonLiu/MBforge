//! Specialist agent base + Literature agent concrete.
//!
//! 设计：把"专项 agent"的差异（prompt / 工具 / 步数）放在 `SpecialistConfig`，
//! 共享的 ReAct 循环 / 审计 / 上下文放在 `SpecialistAgent` 基类。

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::context::LayeredContext;
use super::llm::{LlmClient, LlmResponse, LlmUsage};
use super::observability::{AuditLog, TraceContext};
use super::tools::{ParameterSchema, ToolInfo, ToolRegistry};

// ============================================================================
// 配置
// ============================================================================

/// 派生 agent 的配置
pub struct SpecialistConfig {
    pub name: String,
    pub system_prompt: String,
    pub tool_registry: ToolRegistry,
    pub tools: Option<Vec<String>>,
    pub max_iterations: usize,
    pub max_history_rounds: usize,
    pub audit_tag: String,
    pub per_call_trace: bool,
}

impl SpecialistConfig {
    pub fn literature_agent() -> Self {
        let mut registry = ToolRegistry::new();
        for tool in lit_tools_definitions() {
            registry.register(tool);
        }
        Self {
            name: "literature_agent".to_string(),
            system_prompt: LITERATURE_AGENT_SYSTEM_PROMPT.to_string(),
            tool_registry: registry,
            tools: None,
            max_iterations: 8,
            max_history_rounds: 20,
            audit_tag: "literature_agent".to_string(),
            per_call_trace: true,
        }
    }

    /// 通用 Agent 配置（前端 `agent_chat` / `agent_chat_stream` 用）。
    ///
    /// 与 `literature_agent` 的区别：
    /// - 工具集由 `tool_registry` 注入（调用方负责；典型是从 `ToolExecutor.registry` 借用）
    /// - max_iterations 默认 10（通用 agent 比单文档 agent 步数更多）
    /// - system_prompt 由调用方提供
    pub fn general_agent(
        system_prompt: String,
        tool_registry: ToolRegistry,
        max_iterations: usize,
    ) -> Self {
        Self {
            name: "general_agent".to_string(),
            system_prompt,
            tool_registry,
            tools: None,
            max_iterations,
            max_history_rounds: 20,
            audit_tag: "general_agent".to_string(),
            per_call_trace: true,
        }
    }
}

// ============================================================================
// Base class
// ============================================================================

pub struct SpecialistAgent {
    pub config: SpecialistConfig,
    pub llm: LlmClient,
    pub context: LayeredContext,
    pub audit_log: Option<Arc<AuditLog>>,
    pub project_root: Option<PathBuf>,
}

impl SpecialistAgent {
    pub fn new(
        config: SpecialistConfig,
        llm: LlmClient,
        project_root: Option<&Path>,
    ) -> Self {
        let context = LayeredContext::new(
            &config.system_prompt,
            config.max_history_rounds,
            AGENT_MAX_TOTAL_TOKENS,
        );
        let audit_log = project_root.and_then(|p| AuditLog::new(p).ok().map(Arc::new));
        Self {
            config,
            llm,
            context,
            audit_log,
            project_root: project_root.map(|p| p.to_path_buf()),
        }
    }

    pub fn name(&self) -> &str {
        &self.config.name
    }

    pub fn tool_schemas(&self) -> Vec<Value> {
        let names: Option<std::collections::HashSet<&str>> = self
            .config
            .tools
            .as_ref()
            .map(|v| v.iter().map(|s| s.as_str()).collect());

        self.config
            .tool_registry
            .to_openai_schemas()
            .into_iter()
            .filter(|schema| match &names {
                None => true,
                Some(set) => schema
                    .get("function")
                    .and_then(|f| f.get("name"))
                    .and_then(|n| n.as_str())
                    .map(|n| set.contains(n))
                    .unwrap_or(false),
            })
            .collect()
    }

    /// 单次处理入口
    pub async fn process(
        &mut self,
        user_input: &str,
    ) -> Result<ProcessOutput, String> {
        let mut trace = TraceContext::new();
        trace.span_id = format!("{}.process", self.config.name);

        self.context.add_user_message(user_input);

        let mut iteration: usize = 0;
        let mut tool_calls_log: Vec<ToolCallRecord> = Vec::new();
        let mut final_content = String::new();

        while iteration < self.config.max_iterations {
            iteration += 1;

            let iter_start = std::time::Instant::now();
            let messages = self.context.build_messages(true, true);
            let tool_schemas = self.tool_schemas();
            let tool_schemas_ref = if tool_schemas.is_empty() {
                None
            } else {
                Some(tool_schemas.as_slice())
            };
            let response = self
                .llm
                .chat(&messages, tool_schemas_ref, Some(&trace))
                .await?;
            let iter_ms = iter_start.elapsed().as_millis() as u64;

            if let Some(usage) = &response.usage {
                trace.record_llm_response(
                    self.llm.model_name(),
                    usage.prompt_tokens,
                    usage.completion_tokens,
                );
            }
            if let Some(audit) = &self.audit_log {
                let _ = audit.append_llm_call(
                    &trace.trace_id,
                    Some(&trace.span_id),
                    self.llm.model_name(),
                    response
                        .usage
                        .as_ref()
                        .map(|u| u.prompt_tokens)
                        .unwrap_or(0),
                    response
                        .usage
                        .as_ref()
                        .map(|u| u.completion_tokens)
                        .unwrap_or(0),
                    iter_ms,
                );
            }

            if !response.tool_calls.is_empty() {
                for tc in &response.tool_calls {
                    let tc_start = std::time::Instant::now();
                    let result = self.execute_tool(&tc.name, &tc.arguments, &trace).await;
                    let tc_ms = tc_start.elapsed().as_millis() as u64;

                    if let Some(audit) = &self.audit_log {
                        let _ = audit.append_tool_call(
                            &trace.trace_id,
                            Some(&trace.span_id),
                            &tc.name,
                            &tc.arguments,
                            tc_ms,
                        );
                    }

                    tool_calls_log.push(ToolCallRecord {
                        name: tc.name.clone(),
                        arguments: tc.arguments.clone(),
                        result: result.clone(),
                        duration_ms: tc_ms,
                    });

                    // 把工具结果以 assistant + tool 消息形式灌进 context
                    // 避免调 LayeredContext::add_tool_result —— 它内部用了
                    // 尚未稳定的 `floor_char_boundary`，独立 lib build 会失败。
                    let tool_msg = format!(
                        "[tool_result name={}] {}",
                        tc.name,
                        result.format_for_llm()
                    );
                    // 用 user message 形式记录（OpenAI 兼容 API 不强制
                    // 区分 tool message vs user message，多轮 demo 可用）
                    self.context.add_user_message(&tool_msg);
                }
                continue;
            }

            final_content = response.content.clone();
            self.context.add_assistant_message(&final_content);
            break;
        }

        Ok(ProcessOutput {
            trace_id: trace.trace_id.clone(),
            span_id: trace.span_id.clone(),
            iterations: iteration,
            final_content,
            tool_calls: tool_calls_log,
            tokens: trace.tokens.clone(),
        })
    }

    /// 工具执行 — 派生类 override
    pub async fn execute_tool(
        &self,
        name: &str,
        args: &Value,
        _trace: &TraceContext,
    ) -> ToolResult {
        ToolResult::err(format!(
            "agent `{}` does not implement tool `{}`",
            self.config.name, name
        ))
    }

    pub fn clear(&mut self) {
        self.context.clear_history();
    }
}

// ============================================================================
// ProcessOutput / ToolResult / ToolCallRecord
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcessOutput {
    pub trace_id: String,
    pub span_id: String,
    pub iterations: usize,
    pub final_content: String,
    pub tool_calls: Vec<ToolCallRecord>,
    pub tokens: super::observability::TokenCounter,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolResult {
    pub success: bool,
    pub data: Option<Value>,
    pub message: Option<String>,
    pub error: Option<String>,
}

impl ToolResult {
    pub fn ok(data: Value) -> Self {
        Self {
            success: true,
            data: Some(data),
            message: None,
            error: None,
        }
    }
    pub fn ok_with_msg(data: Value, msg: impl Into<String>) -> Self {
        Self {
            success: true,
            data: Some(data),
            message: Some(msg.into()),
            error: None,
        }
    }
    pub fn err(err: impl Into<String>) -> Self {
        Self {
            success: false,
            data: None,
            message: None,
            error: Some(err.into()),
        }
    }
    /// 序列化成 LLM 友好的字符串
    pub fn format_for_llm(&self) -> String {
        if self.success {
            let data_str = self
                .data
                .as_ref()
                .map(|d| serde_json::to_string_pretty(d).unwrap_or_default())
                .unwrap_or_default();
            match &self.message {
                Some(m) => format!("✓ {}\n{}", m, data_str),
                None => data_str,
            }
        } else {
            format!("✗ ERROR: {}", self.error.as_deref().unwrap_or("unknown"))
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCallRecord {
    pub name: String,
    pub arguments: Value,
    pub result: ToolResult,
    pub duration_ms: u64,
}

// ============================================================================
// LiteratureAgent
// ============================================================================

pub struct LiteratureAgent {
    base: SpecialistAgent,
}

impl LiteratureAgent {
    pub fn new(llm: LlmClient, project_root: Option<&Path>) -> Self {
        let config = SpecialistConfig::literature_agent();
        Self {
            base: SpecialistAgent::new(config, llm, project_root),
        }
    }

    pub fn base_mut(&mut self) -> &mut SpecialistAgent {
        &mut self.base
    }

    pub fn base(&self) -> &SpecialistAgent {
        &self.base
    }

    pub async fn process_extraction(
        &mut self,
        extraction_json: &Value,
    ) -> Result<ProcessOutput, String> {
        let user_input = serde_json::to_string(extraction_json)
            .map_err(|e| format!("Failed to serialize extraction: {}", e))?;
        self.base.process(&user_input).await
    }

    /// Literature agent 的工具实现 — override 基类 execute_tool
    pub async fn execute_lit_tool(
        &self,
        name: &str,
        args: &Value,
        _trace: &TraceContext,
    ) -> ToolResult {
        match name {
            LIT_MOL_REGISTER => lit_mol_register(args).await,
            LIT_NOTE_ADD => lit_note_add(args, self.base.project_root.as_deref()).await,
            LIT_LABEL_APPLY => lit_label_apply(args, self.base.project_root.as_deref()).await,
            LIT_CHEM_VALIDATE => lit_chem_validate(args),
            _ => ToolResult::err(format!(
                "LiteratureAgent: unknown tool `{}`",
                name
            )),
        }
    }
}

// ============================================================================
// 工具名称常量
// ============================================================================

pub const LIT_MOL_REGISTER: &str = "lit_mol_register";
pub const LIT_NOTE_ADD: &str = "lit_note_add";
pub const LIT_LABEL_APPLY: &str = "lit_label_apply";
pub const LIT_CHEM_VALIDATE: &str = "lit_chem_validate";

pub fn lit_tools_definitions() -> Vec<ToolInfo> {
    vec![
        ToolInfo::new(
            LIT_MOL_REGISTER,
            "注册一个分子到项目 molecule store。",
            schema_for_mol_register(),
        ),
        ToolInfo::new(
            LIT_NOTE_ADD,
            "为本次 PDF 处理添加一条结构化笔记到 .mbforge/notes/。",
            schema_for_note_add(),
        ),
        ToolInfo::new(
            LIT_LABEL_APPLY,
            "给某个已注册分子打标签（hits/leads/intermediate 等）。",
            schema_for_label_apply(),
        ),
        ToolInfo::new(
            LIT_CHEM_VALIDATE,
            "校验 SMILES 合法性（纯 Rust chematic，无 sidecar 依赖）。",
            schema_for_chem_validate(),
        ),
    ]
}

// ============================================================================
// 工具实现 — stub（待后续 PR 接到真实后端）
// ============================================================================

async fn lit_mol_register(_args: &Value) -> ToolResult {
    ToolResult::ok_with_msg(
        serde_json::json!({ "mol_id": "stub", "status": "registered" }),
        "Molecule registration deferred to mol_store binding",
    )
}

async fn lit_note_add(_args: &Value, _project_root: Option<&Path>) -> ToolResult {
    ToolResult::ok_with_msg(
        serde_json::json!({ "note_path": "stub" }),
        "Note writing deferred",
    )
}

async fn lit_label_apply(_args: &Value, _project_root: Option<&Path>) -> ToolResult {
    ToolResult::ok_with_msg(
        serde_json::json!({ "label": "stub" }),
        "Label apply deferred",
    )
}

fn lit_chem_validate(args: &Value) -> ToolResult {
    let smiles = match args.get("smiles").and_then(|v| v.as_str()) {
        Some(s) => s,
        None => return ToolResult::err("missing 'smiles' argument"),
    };
    ToolResult::ok(serde_json::json!({
        "valid": !smiles.is_empty() && smiles.len() <= 10000 && !smiles.contains(' '),
        "canonical_smiles": smiles,
        "stub": true,
        "note": "real chematic binding in core/chem.rs",
    }))
}

// ============================================================================
// JSON Schemas
// ============================================================================

fn schema_for_mol_register() -> ParameterSchema {
    let mut p = HashMap::new();
    p.insert("smiles".into(), serde_json::json!({"type": "string"}));
    p.insert("name".into(), serde_json::json!({"type": "string"}));
    p.insert("acronym".into(), serde_json::json!({"type": ["string", "null"]}));
    p.insert(
        "structure_or_phase".into(),
        serde_json::json!({"type": "array", "items": {"type": "string"}}),
    );
    p.insert("category".into(), serde_json::json!({"type": "string"}));
    p
}

fn schema_for_note_add() -> ParameterSchema {
    let mut p = HashMap::new();
    p.insert("doc_id".into(), serde_json::json!({"type": "string"}));
    p.insert("summary".into(), serde_json::json!({"type": "string"}));
    p.insert(
        "key_findings".into(),
        serde_json::json!({"type": "array", "items": {"type": "string"}}),
    );
    p
}

fn schema_for_label_apply() -> ParameterSchema {
    let mut p = HashMap::new();
    p.insert("mol_id".into(), serde_json::json!({"type": "string"}));
    p.insert("label".into(), serde_json::json!({"type": "string"}));
    p
}

fn schema_for_chem_validate() -> ParameterSchema {
    let mut p = HashMap::new();
    p.insert("smiles".into(), serde_json::json!({"type": "string"}));
    p
}

// ============================================================================
// Constants
// ============================================================================

const AGENT_MAX_TOTAL_TOKENS: usize = 8192;

const LITERATURE_AGENT_SYSTEM_PROMPT: &str = r#"你是文献处理 agent — **最上游**的角色。

# 输入
- PDF 抽取结果（结构化 JSON）：compounds / activities / key_findings
- 不要再做抽取

# 工具（4 个）
- `lit_mol_register` — 注册分子到项目 molecule store
- `lit_note_add` — 添加结构化笔记
- `lit_label_apply` — 给已注册分子打标签
- `lit_chem_validate` — 校验 SMILES 合法性

# 输出
- 自然语言总结：注册了哪些分子 / 哪些需要人工审核 / 关键发现
- 不需要再调下游工具

# 规则
1. 一次 process() 调 = 一次完整处理，不要跨调用维持上下文
2. 不在工具集里：不要试图调 KB search / file read / literature search
3. 遇到 SMILES 合法性问题：先调 `lit_chem_validate`，失败则不调 `lit_mol_register`
4. 批量注册：使用多次 `lit_mol_register` 调用，一次注册一个分子
5. 置信度诚实：description 不清晰就改用 `lit_note_add` 留待人工审核
"#;

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_tool_result_format() {
        let ok = ToolResult::ok(json!({"id": 1}));
        assert!(ok.success);
        let formatted = ok.format_for_llm();
        assert!(formatted.contains("\"id\": 1"));
        assert!(!formatted.contains("ERROR"));

        let err = ToolResult::err("smiles invalid");
        assert!(!err.success);
        let formatted = err.format_for_llm();
        assert!(formatted.contains("ERROR"));
        assert!(formatted.contains("smiles invalid"));
    }

    #[test]
    fn test_lit_chem_validate_works() {
        let r = lit_chem_validate(&json!({"smiles": "CCO"}));
        assert!(r.success);
        let d = r.data.unwrap();
        assert_eq!(d["valid"], true);
    }

    #[test]
    fn test_lit_chem_validate_rejects_empty() {
        let r = lit_chem_validate(&json!({"smiles": ""}));
        assert!(r.success);
        let d = r.data.unwrap();
        assert_eq!(d["valid"], false);
    }

    #[test]
    fn test_lit_tools_definitions_count() {
        let defs = lit_tools_definitions();
        assert_eq!(defs.len(), 4);
        let names: Vec<&str> = defs.iter().map(|t| t.name.as_str()).collect();
        assert!(names.contains(&LIT_MOL_REGISTER));
        assert!(names.contains(&LIT_NOTE_ADD));
        assert!(names.contains(&LIT_LABEL_APPLY));
        assert!(names.contains(&LIT_CHEM_VALIDATE));
    }

    #[test]
    fn test_specialist_config_literature_agent() {
        let cfg = SpecialistConfig::literature_agent();
        assert_eq!(cfg.name, "literature_agent");
        assert!(cfg.system_prompt.contains("文献处理 agent"));
        assert!(cfg.tool_registry.get(LIT_MOL_REGISTER).is_some());
        assert_eq!(cfg.max_iterations, 8);
    }

    #[test]
    fn test_tool_schemas_filter_by_whitelist() {
        use std::collections::HashSet;

        let mut cfg = SpecialistConfig::literature_agent();
        cfg.tools = Some(vec![LIT_MOL_REGISTER.to_string()]);

        let llm = LlmClient::new(&crate::core::config::settings::ModelConfig::default());
        let agent = SpecialistAgent::new(cfg, llm, None);
        let schemas = agent.tool_schemas();

        // 4 个工具，1 个白名单 → 应该只剩 1 个
        assert_eq!(schemas.len(), 1);
        let name: String = schemas[0]["function"]["name"].as_str().unwrap().to_string();
        assert_eq!(name, LIT_MOL_REGISTER);
    }

    #[test]
    fn test_execute_tool_default_returns_err() {
        let rt = tokio::runtime::Runtime::new().unwrap();
        rt.block_on(async {
            let cfg = SpecialistConfig::literature_agent();
            let llm = LlmClient::new(&crate::core::config::settings::ModelConfig::default());
            let agent = SpecialistAgent::new(cfg, llm, None);
            let trace = TraceContext::new();
            let r = agent
                .execute_tool("nonexistent_tool", &json!({}), &trace)
                .await;
            assert!(!r.success);
            assert!(r.error.unwrap().contains("does not implement"));
        });
    }
}
