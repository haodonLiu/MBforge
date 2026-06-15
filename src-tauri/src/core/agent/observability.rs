#![allow(dead_code)]
//! 可观测性层 — 结构化 tracing、token 追踪、审计日志
//!
//! 覆盖 Layer 5 (Observability) 基础设施。
//!
//! 设计原则：
//! - `TraceContext` 在操作入口创建，通过 HTTP Header (`X-Trace-Id` / `X-Span-Id`)
//!   传播到 Python sidecar，实现跨边界关联。
//! - `TokenCounter` 在每次 LLM / Embedding 调用后累加。
//! - `AuditLog` 追加写入 `.mbforge/audit.jsonl`，每行一个 JSON。
//!
//! 预算（cost / budget / BudgetEnforcer）已显式移出本模块 — 留给上层
//! 业务策略层处理，不在基础设施层强制限制。

use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::Instant;

use crate::core::helpers::now_secs_f64;

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
        }
    }

    /// 创建子 span，共享 trace_id 和 token 计数。
    pub fn child(&self, span_name: &str) -> Self {
        Self {
            trace_id: self.trace_id.clone(),
            span_id: format!("{}-{}", self.span_id, span_name),
            parent_span_id: Some(self.span_id.clone()),
            started_at: Instant::now(),
            tokens: self.tokens.clone(),
        }
    }

    /// 已流逝时间（毫秒）。
    pub fn elapsed_ms(&self) -> u64 {
        self.started_at.elapsed().as_millis() as u64
    }

    /// 记录一次 LLM 调用的 token 消耗。
    ///
    /// # Arguments
    /// - `model`: LLM 模型名称（仅作为审计字段记录，不做费用估算）
    /// - `prompt_tokens`: 提示 token 数
    /// - `completion_tokens`: 响应 token 数
    pub fn record_llm_response(
        &mut self,
        _model: &str,
        prompt_tokens: u64,
        completion_tokens: u64,
    ) {
        self.tokens
            .record_llm_call(prompt_tokens, completion_tokens);
    }

    /// 把当前 trace 信息转成 HTTP Header 列表。
    ///
    /// 调用方在拼 `reqwest::RequestBuilder` 时插入：
    /// ```ignore
    /// for (k, v) in trace.to_headers() {
    ///     req = req.header(k, v);
    /// }
    /// ```
    pub fn to_headers(&self) -> Vec<(&'static str, String)> {
        vec![
            ("X-Trace-Id", self.trace_id.clone()),
            ("X-Span-Id", self.span_id.clone()),
        ]
    }
}

impl Default for TraceContext {
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
    pub span_id: Option<String>,
    pub timestamp: f64,
    pub action: String, // "llm_call" | "tool_call" | "file_write" | "molecule_add"
    pub details: serde_json::Value,
    pub tokens_used: u64,
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
        writeln!(file, "{}", line).map_err(|e| format!("Failed to write audit log: {}", e))?;
        // 强制 flush + fsync: 审计日志不能丢
        file.flush().map_err(|e| format!("Flush failed: {}", e))?;
        file.sync_all()
            .map_err(|e| format!("Fsync failed: {}", e))?;
        Ok(())
    }

    /// 记录一次 LLM 调用。
    pub fn append_llm_call(
        &self,
        trace_id: &str,
        span_id: Option<&str>,
        model: &str,
        prompt_tokens: u64,
        completion_tokens: u64,
        duration_ms: u64,
    ) -> Result<(), String> {
        self.append(&AuditEntry {
            trace_id: trace_id.to_string(),
            span_id: span_id.map(|s| s.to_string()),
            timestamp: now_secs_f64(),
            action: "llm_call".to_string(),
            details: serde_json::json!({
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }),
            tokens_used: prompt_tokens + completion_tokens,
            duration_ms,
        })
    }

    /// 记录一次工具调用。
    pub fn append_tool_call(
        &self,
        trace_id: &str,
        span_id: Option<&str>,
        tool_name: &str,
        args: &serde_json::Value,
        duration_ms: u64,
    ) -> Result<(), String> {
        self.append(&AuditEntry {
            trace_id: trace_id.to_string(),
            span_id: span_id.map(|s| s.to_string()),
            timestamp: now_secs_f64(),
            action: "tool_call".to_string(),
            details: serde_json::json!({
                "tool": tool_name,
                "arguments": args,
            }),
            tokens_used: 0,
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
            span_id: None,
            timestamp: now_secs_f64(),
            action: "molecule_add".to_string(),
            details: serde_json::json!({
                "mol_id": mol_id,
                "smiles": smiles,
            }),
            tokens_used: 0,
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

    /// 按 trace_id 过滤（最近的 N 条，按时间倒序）。
    pub fn read_by_trace(&self, trace_id: &str, limit: usize) -> Result<Vec<AuditEntry>, String> {
        let mut entries = self.read_all()?;
        entries.reverse(); // 最新的在前面
        entries.retain(|e| e.trace_id == trace_id);
        entries.truncate(limit);
        Ok(entries)
    }
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
    fn test_trace_context_to_headers() {
        let ctx = TraceContext::new();
        let headers = ctx.to_headers();
        assert_eq!(headers.len(), 2);
        assert_eq!(headers[0].0, "X-Trace-Id");
        assert_eq!(headers[1].0, "X-Span-Id");
        assert_eq!(headers[0].1, ctx.trace_id);
        assert_eq!(headers[1].1, ctx.span_id);
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
    fn test_token_counter_record_embedding_call() {
        let mut tc = TokenCounter::default();
        tc.record_embedding_call(50);
        tc.record_embedding_call(30);
        assert_eq!(tc.embedding_calls, 2);
        assert_eq!(tc.prompt_tokens, 80);
    }

    #[test]
    fn test_trace_context_record_llm_response() {
        let mut ctx = TraceContext::new();
        ctx.record_llm_response("gpt-4", 1000, 500);
        assert_eq!(ctx.tokens.llm_calls, 1);
        assert_eq!(ctx.tokens.prompt_tokens, 1000);
        assert_eq!(ctx.tokens.completion_tokens, 500);
    }

    #[test]
    fn test_audit_log_append_and_read() {
        let tmp = tempfile::tempdir().unwrap();
        let log = AuditLog::new(tmp.path()).unwrap();

        let entry = AuditEntry {
            trace_id: "t1".to_string(),
            span_id: Some("root-step1".to_string()),
            timestamp: 1234.0,
            action: "llm_call".to_string(),
            details: serde_json::json!({"model": "qwen"}),
            tokens_used: 150,
            duration_ms: 200,
        };
        log.append(&entry).unwrap();

        let entries = log.read_all().unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].trace_id, "t1");
        assert_eq!(entries[0].action, "llm_call");
        assert_eq!(entries[0].tokens_used, 150);
        assert_eq!(entries[0].span_id.as_deref(), Some("root-step1"));
    }

    #[test]
    fn test_audit_log_append_llm_call() {
        let tmp = tempfile::tempdir().unwrap();
        let log = AuditLog::new(tmp.path()).unwrap();
        log.append_llm_call("trace-1", Some("span-1"), "qwen", 100, 50, 300)
            .unwrap();

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
        log.append_tool_call(
            "trace-2",
            None,
            "search",
            &serde_json::json!({"q": "aspirin"}),
            150,
        )
        .unwrap();

        let entries = log.read_all().unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].action, "tool_call");
        assert_eq!(entries[0].details["tool"], "search");
    }

    #[test]
    fn test_audit_log_read_by_trace() {
        let tmp = tempfile::tempdir().unwrap();
        let log = AuditLog::new(tmp.path()).unwrap();
        log.append_llm_call("trace-A", None, "m", 10, 10, 100)
            .unwrap();
        log.append_tool_call("trace-B", None, "t", &serde_json::json!({}), 50)
            .unwrap();
        log.append_llm_call("trace-A", None, "m", 20, 20, 200)
            .unwrap();

        let only_a = log.read_by_trace("trace-A", 10).unwrap();
        assert_eq!(only_a.len(), 2);
        assert!(only_a.iter().all(|e| e.trace_id == "trace-A"));
        // 倒序
        assert_eq!(only_a[0].duration_ms, 200);
    }
}
