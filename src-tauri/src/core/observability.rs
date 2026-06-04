//! 可观测性层 — 结构化 tracing、token/cost 追踪、审计日志、预算执行
//!
//! 覆盖 Layer 5 (Observability) + Layer 7 (Governance) 基础设施。
//!
//! 设计原则：
//! - TraceContext 在操作入口创建，通过 HTTP Header 传播到 Python sidecar
//! - TokenCounter 在每个 LLM/Embedding 调用后累加
//! - BudgetEnforcer 在每次调用前检查，超预算时返回 BudgetExceeded
//! - AuditLog 追加写入 `.mbforge/audit.jsonl`，每行一个 JSON

use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::Instant;

use serde::{Deserialize, Serialize};
use uuid::Uuid;

// ---------------------------------------------------------------------------
// TokenCounter
// ---------------------------------------------------------------------------

/// Token 消耗计数器，追踪 prompt / completion / embedding / llm_call 次数。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TokenCounter {
    pub prompt_tokens: u64,
    pub completion_tokens: u64,
    pub embedding_calls: u64,
    pub llm_calls: u64,
}

impl TokenCounter {
    /// 总 token 数（prompt + completion）。
    pub fn total_tokens(&self) -> u64 {
        self.prompt_tokens + self.completion_tokens
    }

    /// 记录一次 LLM 调用的 token 消耗。
    pub fn record_llm_call(&mut self, prompt: u64, completion: u64) {
        self.llm_calls += 1;
        self.prompt_tokens += prompt;
        self.completion_tokens += completion;
    }

    /// 记录一次 Embedding 调用的 token 消耗。
    pub fn record_embedding_call(&mut self, tokens: u64) {
        self.embedding_calls += 1;
        self.prompt_tokens += tokens;
    }
}

// ---------------------------------------------------------------------------
// TraceContext
// ---------------------------------------------------------------------------

/// 追踪上下文 — 贯穿一次完整操作（对话或文档处理）。
///
/// `trace_id` 在创建时通过 UUID v4 生成，通过 `X-Trace-Id` HTTP Header
/// 传播到 Python sidecar，实现跨边界关联。
#[derive(Debug, Clone)]
pub struct TraceContext {
    pub trace_id: String,
    pub span_id: String,
    pub parent_span_id: Option<String>,
    pub started_at: Instant,
    pub tokens: TokenCounter,
    pub cost_estimate: f64,
}

impl TraceContext {
    /// 创建新的 TraceContext，生成新的 UUID v4 trace_id。
    pub fn new() -> Self {
        Self {
            trace_id: Uuid::new_v4().to_string(),
            span_id: "root".to_string(),
            parent_span_id: None,
            started_at: Instant::now(),
            tokens: TokenCounter::default(),
            cost_estimate: 0.0,
        }
    }

    /// 创建子 span，共享 trace_id 和 token/cost 计数。
    pub fn child(&self, span_name: &str) -> Self {
        Self {
            trace_id: self.trace_id.clone(),
            span_id: format!("{}-{}", self.span_id, span_name),
            parent_span_id: Some(self.span_id.clone()),
            started_at: Instant::now(),
            tokens: self.tokens.clone(),
            cost_estimate: self.cost_estimate,
        }
    }

    /// 已流逝时间（毫秒）。
    pub fn elapsed_ms(&self) -> u64 {
        self.started_at.elapsed().as_millis() as u64
    }

    /// 记录 LLM 响应中的 usage 信息，并累加 cost。
    pub fn record_llm_response(&mut self, model: &str, prompt_tokens: u64, completion_tokens: u64) {
        self.tokens.record_llm_call(prompt_tokens, completion_tokens);
        self.cost_estimate += estimate_cost(model, prompt_tokens, completion_tokens);
    }
}

impl Default for TraceContext {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// Cost estimation
// ---------------------------------------------------------------------------

/// 估算单次 LLM 调用的费用（USD）。
///
/// 价格基于公开 API 定价（$ / 1K tokens），对未知模型使用保守默认值。
pub fn estimate_cost(model: &str, prompt_tokens: u64, completion_tokens: u64) -> f64 {
    let model_lower = model.to_lowercase();
    // (prompt_price_per_1k, completion_price_per_1k)
    let (prompt_price, completion_price) = if model_lower.contains("gpt-4o") {
        (0.005, 0.015)
    } else if model_lower.contains("gpt-4") {
        (0.03, 0.06)
    } else if model_lower.contains("claude-3-opus") {
        (0.015, 0.075)
    } else if model_lower.contains("claude-3-sonnet") || model_lower.contains("claude-3-5-sonnet") {
        (0.003, 0.015)
    } else if model_lower.contains("claude-3-haiku") {
        (0.00025, 0.00125)
    } else if model_lower.contains("qwen") || model_lower.contains("deepseek") {
        // 国产/开源模型：极低价格
        (0.0005, 0.001)
    } else {
        // 默认保守估计
        (0.001, 0.002)
    };

    let prompt_cost = (prompt_tokens as f64 / 1000.0) * prompt_price;
    let completion_cost = (completion_tokens as f64 / 1000.0) * completion_price;
    prompt_cost + completion_cost
}

// ---------------------------------------------------------------------------
// BudgetEnforcer
// ---------------------------------------------------------------------------

/// 预算超限错误。
#[derive(Debug, Clone)]
pub struct BudgetExceeded {
    pub kind: BudgetKind,
    pub limit: f64,
    pub current: f64,
}

impl std::fmt::Display for BudgetExceeded {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "Budget exceeded: {:?} limit={:.2} current={:.2}",
            self.kind, self.limit, self.current
        )
    }
}

/// 预算类型。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BudgetKind {
    Tokens,
    Cost,
    LlmCalls,
}

/// 剩余预算快照。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BudgetRemaining {
    pub tokens: u64,
    pub cost: f64,
    pub llm_calls: usize,
}

/// 预算执行器 — 每次 LLM/Embedding 调用前检查，超预算时拒绝。
///
/// 默认限制：
/// - 每 session 100K tokens
/// - 每 session $1.00
/// - 每 document 50 次 LLM 调用
#[derive(Debug, Clone)]
pub struct BudgetEnforcer {
    pub max_tokens_per_session: u64,
    pub max_cost_per_session: f64,
    pub max_llm_calls_per_document: usize,
    current: TokenCounter,
    current_cost: f64,
    current_llm_calls: usize,
}

impl BudgetEnforcer {
    /// 使用默认限制创建 BudgetEnforcer。
    pub fn new() -> Self {
        Self {
            max_tokens_per_session: 100_000,
            max_cost_per_session: 1.00,
            max_llm_calls_per_document: 50,
            current: TokenCounter::default(),
            current_cost: 0.0,
            current_llm_calls: 0,
        }
    }

    /// 使用自定义限制创建 BudgetEnforcer。
    pub fn with_limits(max_tokens: u64, max_cost: f64, max_llm_calls: usize) -> Self {
        Self {
            max_tokens_per_session: max_tokens,
            max_cost_per_session: max_cost,
            max_llm_calls_per_document: max_llm_calls,
            current: TokenCounter::default(),
            current_cost: 0.0,
            current_llm_calls: 0,
        }
    }

    /// 检查预估消耗是否仍在预算内。
    ///
    /// 在发起 LLM 调用前调用。如果超预算，返回 `Err(BudgetExceeded)`。
    pub fn check(&self, estimated_tokens: u64) -> Result<(), BudgetExceeded> {
        let total = self.current.total_tokens() + estimated_tokens;
        if total > self.max_tokens_per_session {
            return Err(BudgetExceeded {
                kind: BudgetKind::Tokens,
                limit: self.max_tokens_per_session as f64,
                current: total as f64,
            });
        }

        let estimated_cost = estimate_cost("default", estimated_tokens, estimated_tokens / 2);
        let projected_cost = self.current_cost + estimated_cost;
        if projected_cost > self.max_cost_per_session {
            return Err(BudgetExceeded {
                kind: BudgetKind::Cost,
                limit: self.max_cost_per_session,
                current: projected_cost,
            });
        }

        if self.current_llm_calls >= self.max_llm_calls_per_document {
            return Err(BudgetExceeded {
                kind: BudgetKind::LlmCalls,
                limit: self.max_llm_calls_per_document as f64,
                current: self.current_llm_calls as f64,
            });
        }

        Ok(())
    }

    /// 记录实际消耗（用于 Embedding 等不调用 LLM 的场景）。
    pub fn record(&mut self, actual_tokens: u64, cost: f64) {
        self.current.prompt_tokens += actual_tokens;
        self.current_cost += cost;
    }

    /// 记录一次完整的 LLM 调用消耗。
    pub fn record_llm_call(&mut self, prompt_tokens: u64, completion_tokens: u64, model: &str) {
        self.current_llm_calls += 1;
        self.current.record_llm_call(prompt_tokens, completion_tokens);
        self.current_cost += estimate_cost(model, prompt_tokens, completion_tokens);
    }

    /// 获取剩余预算。
    pub fn remaining(&self) -> BudgetRemaining {
        BudgetRemaining {
            tokens: self.max_tokens_per_session.saturating_sub(self.current.total_tokens()),
            cost: (self.max_cost_per_session - self.current_cost).max(0.0),
            llm_calls: self.max_llm_calls_per_document.saturating_sub(self.current_llm_calls),
        }
    }

    /// 获取当前消耗统计。
    pub fn current_usage(&self) -> &TokenCounter {
        &self.current
    }

    /// 获取当前总费用。
    pub fn current_cost(&self) -> f64 {
        self.current_cost
    }

    /// 获取当前 LLM 调用次数。
    pub fn current_llm_calls(&self) -> usize {
        self.current_llm_calls
    }
}

impl Default for BudgetEnforcer {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// AuditLog
// ---------------------------------------------------------------------------

/// 审计日志条目 — 每行一个 JSONL 记录。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditEntry {
    pub trace_id: String,
    pub timestamp: f64,
    pub action: String,
    pub details: serde_json::Value,
    pub tokens_used: u64,
    pub cost: f64,
    pub duration_ms: u64,
}

/// 审计日志 — 追加写入 `.mbforge/audit.jsonl`。
pub struct AuditLog {
    path: PathBuf,
    file: Arc<Mutex<File>>,
}

impl AuditLog {
    /// 打开或创建审计日志文件。
    pub fn new(project_root: &Path) -> Result<Self, String> {
        let audit_dir = project_root.join(".mbforge");
        std::fs::create_dir_all(&audit_dir)
            .map_err(|e| format!("Failed to create audit dir: {}", e))?;
        let path = audit_dir.join("audit.jsonl");

        let file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&path)
            .map_err(|e| format!("Failed to open audit log: {}", e))?;

        Ok(Self {
            path,
            file: Arc::new(Mutex::new(file)),
        })
    }

    /// 追加一条审计记录。
    pub fn append(&self, entry: &AuditEntry) -> Result<(), String> {
        let line = serde_json::to_string(entry)
            .map_err(|e| format!("Failed to serialize audit entry: {}", e))?;
        let mut file = self
            .file
            .lock()
            .map_err(|e| format!("Audit log lock poisoned: {}", e))?;
        writeln!(file, "{}", line)
            .map_err(|e| format!("Failed to write audit log: {}", e))?;
        Ok(())
    }

    /// 记录一次 LLM 调用。
    pub fn append_llm_call(
        &self,
        trace_id: &str,
        model: &str,
        prompt_tokens: u64,
        completion_tokens: u64,
        duration_ms: u64,
    ) -> Result<(), String> {
        let cost = estimate_cost(model, prompt_tokens, completion_tokens);
        self.append(&AuditEntry {
            trace_id: trace_id.to_string(),
            timestamp: now_secs(),
            action: "llm_call".to_string(),
            details: serde_json::json!({
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }),
            tokens_used: prompt_tokens + completion_tokens,
            cost,
            duration_ms,
        })
    }

    /// 记录一次工具调用。
    pub fn append_tool_call(
        &self,
        trace_id: &str,
        tool_name: &str,
        args: &serde_json::Value,
        duration_ms: u64,
    ) -> Result<(), String> {
        self.append(&AuditEntry {
            trace_id: trace_id.to_string(),
            timestamp: now_secs(),
            action: "tool_call".to_string(),
            details: serde_json::json!({
                "tool": tool_name,
                "arguments": args,
            }),
            tokens_used: 0,
            cost: 0.0,
            duration_ms,
        })
    }

    /// 记录一次分子添加操作。
    pub fn append_molecule_add(
        &self,
        trace_id: &str,
        mol_id: &str,
        smiles: &str,
    ) -> Result<(), String> {
        self.append(&AuditEntry {
            trace_id: trace_id.to_string(),
            timestamp: now_secs(),
            action: "molecule_add".to_string(),
            details: serde_json::json!({
                "mol_id": mol_id,
                "smiles": smiles,
            }),
            tokens_used: 0,
            cost: 0.0,
            duration_ms: 0,
        })
    }

    /// 读取全部审计记录。
    pub fn read_all(&self) -> Result<Vec<AuditEntry>, String> {
        let file =
            File::open(&self.path).map_err(|e| format!("Failed to open audit log: {}", e))?;
        let reader = BufReader::new(file);
        let mut entries = Vec::new();
        for line in reader.lines() {
            let line = line.map_err(|e| format!("Read error: {}", e))?;
            if line.trim().is_empty() {
                continue;
            }
            if let Ok(entry) = serde_json::from_str::<AuditEntry>(&line) {
                entries.push(entry);
            }
        }
        Ok(entries)
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn now_secs() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_trace_context_new_generates_uuid() {
        let ctx = TraceContext::new();
        // UUID v4 格式: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
        assert_eq!(ctx.trace_id.len(), 36);
        assert_eq!(ctx.trace_id.chars().nth(14), Some('4'));
        assert_eq!(ctx.span_id, "root");
        assert!(ctx.parent_span_id.is_none());
    }

    #[test]
    fn test_trace_context_child_inherits_trace_id() {
        let parent = TraceContext::new();
        let child = parent.child("step1");
        assert_eq!(child.trace_id, parent.trace_id);
        assert_eq!(child.parent_span_id, Some("root".to_string()));
        assert_eq!(child.span_id, "root-step1");
    }

    #[test]
    fn test_token_counter_record_llm_call() {
        let mut tc = TokenCounter::default();
        tc.record_llm_call(100, 50);
        tc.record_llm_call(200, 80);
        assert_eq!(tc.llm_calls, 2);
        assert_eq!(tc.prompt_tokens, 300);
        assert_eq!(tc.completion_tokens, 130);
        assert_eq!(tc.total_tokens(), 430);
    }

    #[test]
    fn test_budget_enforcer_check_passes_within_limit() {
        let be = BudgetEnforcer::new();
        assert!(be.check(1000).is_ok());
    }

    #[test]
    fn test_budget_enforcer_check_exceeds_tokens() {
        let mut be = BudgetEnforcer::with_limits(1000, 100.0, 100);
        be.record(900, 0.0);
        let err = be.check(200).unwrap_err();
        assert_eq!(err.kind, BudgetKind::Tokens);
        assert_eq!(err.limit, 1000.0);
        assert_eq!(err.current, 1100.0);
    }

    #[test]
    fn test_budget_enforcer_check_exceeds_llm_calls() {
        let mut be = BudgetEnforcer::with_limits(1_000_000, 100.0, 2);
        be.record_llm_call(10, 10, "test");
        be.record_llm_call(10, 10, "test");
        // 第 3 次应超限
        let err = be.check(10).unwrap_err();
        assert_eq!(err.kind, BudgetKind::LlmCalls);
    }

    #[test]
    fn test_budget_enforcer_remaining() {
        let mut be = BudgetEnforcer::with_limits(1000, 10.0, 5);
        be.record_llm_call(100, 50, "test");
        let rem = be.remaining();
        assert_eq!(rem.tokens, 850);
        assert_eq!(rem.llm_calls, 4);
        assert!(rem.cost > 0.0 && rem.cost < 10.0);
    }

    #[test]
    fn test_estimate_cost_known_models() {
        // GPT-4: 1K prompt + 1K completion = $0.03 + $0.06 = $0.09
        let cost = estimate_cost("gpt-4", 1000, 1000);
        assert!((cost - 0.09).abs() < 0.001);

        // Claude-3 Haiku: 便宜
        let cost_haiku = estimate_cost("claude-3-haiku", 1000, 1000);
        assert!(cost_haiku < cost);
    }

    #[test]
    fn test_audit_log_append_and_read() {
        let tmp = tempfile::tempdir().unwrap();
        let log = AuditLog::new(tmp.path()).unwrap();

        let entry = AuditEntry {
            trace_id: "t1".to_string(),
            timestamp: 1234.0,
            action: "llm_call".to_string(),
            details: serde_json::json!({"model": "qwen"}),
            tokens_used: 150,
            cost: 0.001,
            duration_ms: 200,
        };
        log.append(&entry).unwrap();

        let entries = log.read_all().unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].trace_id, "t1");
        assert_eq!(entries[0].action, "llm_call");
        assert_eq!(entries[0].tokens_used, 150);
    }

    #[test]
    fn test_audit_log_append_llm_call() {
        let tmp = tempfile::tempdir().unwrap();
        let log = AuditLog::new(tmp.path()).unwrap();
        log.append_llm_call("trace-1", "qwen", 100, 50, 300).unwrap();

        let entries = log.read_all().unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].trace_id, "trace-1");
        assert_eq!(entries[0].action, "llm_call");
        assert_eq!(entries[0].tokens_used, 150);
        assert_eq!(entries[0].duration_ms, 300);
    }

    #[test]
    fn test_audit_log_append_tool_call() {
        let tmp = tempfile::tempdir().unwrap();
        let log = AuditLog::new(tmp.path()).unwrap();
        log.append_tool_call("trace-2", "search", &serde_json::json!({"q": "aspirin"}), 150)
            .unwrap();

        let entries = log.read_all().unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].action, "tool_call");
        assert_eq!(entries[0].details["tool"], "search");
    }
}
