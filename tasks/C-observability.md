# Task C: 可观测性层

> 难度: ★★★☆☆ (Medium)
> 优先级: P1 — 架构补齐
> 预计工作量: 2-3 天
> 依赖: 无（可立即开始）
> 被依赖: 无

---

## 目标

建立 Layer 5（可观测性）+ Layer 7（治理）基础设施：结构化 tracing、token/cost 追踪、审计日志、预算执行。

---

## 当前问题

| 缺失 | 影响 | ETCLOVG 层 |
|------|------|-----------|
| 无结构化 tracing | 跨 Rust↔Python 调用无法追踪 | L5 |
| 无 token/cost 统计 | 不知道一次对话消耗多少资源 | L7 |
| 无审计日志 | Agent 决策不可追溯 | L7 |
| 无预算执行 | Agent 可以无限消耗 token | L7 |
| 无跨边界关联 ID | Rust 和 Python 的日志无法关联 | L5 |

---

## 设计规范

### TraceContext

```rust
pub struct TraceContext {
    pub trace_id: String,       // 端到端追踪 ID（UUID）
    pub span_id: String,        // 当前操作 ID
    pub parent_span_id: Option<String>,
    pub started_at: Instant,
    pub tokens: TokenCounter,
    pub cost_estimate: f64,
}

pub struct TokenCounter {
    pub prompt_tokens: u64,
    pub completion_tokens: u64,
    pub embedding_calls: u64,
    pub llm_calls: u64,
    pub total_tokens: u64,      // 自动聚合
}
```

### 跨边界传播

```
Rust pipeline Stage 2
  → HTTP POST /api/v1/llm/chat
    Header: X-Trace-Id: {trace_id}
    Header: X-Span-Id: stage2-section3

Python sidecar 收到
  → 记录: trace={trace_id}, span=stage2-section3, model=qwen, tokens=1500
  → 返回响应

Rust 收到响应
  → trace_ctx.tokens.llm_calls += 1
  → trace_ctx.tokens.prompt_tokens += response.usage.prompt_tokens
  → trace_ctx.cost_estimate += estimate_cost(response.usage, model)
```

### BudgetEnforcer

```rust
pub struct BudgetEnforcer {
    pub max_tokens_per_session: u64,      // 默认 100K
    pub max_cost_per_session: f64,         // 默认 $1.00
    pub max_llm_calls_per_document: usize, // 默认 50
    pub current: TokenCounter,
}

impl BudgetEnforcer {
    pub fn check(&self, estimated_tokens: u64) -> Result<(), BudgetExceeded>;
    pub fn record(&mut self, actual_tokens: u64, cost: f64);
    pub fn remaining(&self) -> BudgetRemaining;
}
```

### AuditLog

```rust
pub struct AuditEntry {
    pub trace_id: String,
    pub timestamp: f64,
    pub action: String,           // "llm_call" | "tool_call" | "file_write" | "molecule_add"
    pub details: serde_json::Value,
    pub tokens_used: u64,
    pub cost: f64,
    pub duration_ms: u64,
}
```

持久化到 `.mbforge/audit.jsonl`（追加写入，每行一个 JSON）。

---

## 实施步骤

### Step 1: observability.rs 模块
- [ ] `TraceContext` + `TokenCounter` 定义
- [ ] `TraceContext::new()` — 生成 trace_id
- [ ] `TraceContext::child()` — 创建子 span
- [ ] `TokenCounter::record_llm_call()` — 记录 LLM 调用
- [ ] `estimate_cost()` — 根据模型和 token 数估算费用

### Step 2: 跨边界传播
- [ ] `LlmClient::chat()` — 请求时注入 `X-Trace-Id` / `X-Span-Id` header
- [ ] `SidecarEmbedder::embed()` — 同上
- [ ] Python sidecar — 从 header 读取 trace_id，记录到日志

### Step 3: BudgetEnforcer
- [ ] 定义 `BudgetEnforcer` struct
- [ ] 在 `Agent::chat()` 入口检查预算
- [ ] 在每次 LLM 调用后记录消耗
- [ ] 超预算时返回 `BudgetExceeded` 错误

### Step 4: AuditLog
- [ ] `AuditLog` struct — 追加写入 `.mbforge/audit.jsonl`
- [ ] 在关键操作处记录：LLM 调用、工具执行、文件写入、分子添加
- [ ] Tauri 命令 `audit_log_get()` — 查询审计日志

### Step 5: 集成
- [ ] `Agent::chat()` 中创建 `TraceContext`，贯穿整个对话
- [ ] `process_document()` 中创建 `TraceContext`，贯穿所有 Stage
- [ ] 前端 Settings 页面显示 token/cost 统计

---

## 文件范围

| 文件 | 操作 |
|------|------|
| `src-tauri/src/core/observability.rs` | 新建 |
| `src-tauri/src/core/llm.rs` | 修改（注入 trace header） |
| `src-tauri/src/core/agent.rs` | 修改（创建 TraceContext + BudgetEnforcer） |
| `src-tauri/src/parsers/pipeline.rs` | 修改（创建 TraceContext） |
| `src-tauri/src/core/mod.rs` | 修改（添加模块声明） |
| `src/mbforge/model_server/main.py` | 修改（读取 trace header） |

---

## 上下文索引

| 参考 | 位置 | 说明 |
|------|------|------|
| LlmClient | `src-tauri/src/core/llm.rs` | HTTP 客户端，需注入 header |
| Agent::chat | `src-tauri/src/core/agent.rs` | ReAct 循环入口 |
| process_document | `src-tauri/src/parsers/pipeline.rs` | 管线入口 |
| Python main.py | `src/mbforge/model_server/main.py` | sidecar 入口 |
| ARCHITECTURE.md §九 | `ARCHITECTURE.md` | 可观测性架构 |
| ARCHITECTURE.md §十 | `ARCHITECTURE.md` | 治理架构 |
| STANDARDS.md | `tasks/STANDARDS.md` | 开发规范 |
