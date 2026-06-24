//! 追踪上下文 — trace propagation 到 Python sidecar
//!
//! Extracted from the archived agent module. Used by `core/vector/embedding.rs`
//! to inject X-Trace-Id / X-Span-Id headers into sidecar HTTP requests.

use std::time::Instant;

use uuid::Uuid;

/// Token 消耗计数器
#[derive(Debug, Clone, Default)]
pub struct TokenCounter {
    pub prompt_tokens: u64,
    pub completion_tokens: u64,
    pub embedding_calls: u64,
    pub llm_calls: u64,
}

impl TokenCounter {
    pub fn total_tokens(&self) -> u64 {
        self.prompt_tokens + self.completion_tokens
    }
}

/// 追踪上下文 — 贯穿一次完整操作
///
/// `trace_id` 通过 UUID v4 生成，通过 `X-Trace-Id` HTTP Header
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
    pub fn new() -> Self {
        Self {
            trace_id: Uuid::new_v4().to_string(),
            span_id: "root".to_string(),
            parent_span_id: None,
            started_at: Instant::now(),
            tokens: TokenCounter::default(),
        }
    }

    /// 把当前 trace 信息转成 HTTP Header 列表
    pub fn to_headers(&self) -> [(&'static str, &str); 2] {
        [("X-Trace-Id", &self.trace_id), ("X-Span-Id", &self.span_id)]
    }
}

impl Default for TraceContext {
    fn default() -> Self {
        Self::new()
    }
}
