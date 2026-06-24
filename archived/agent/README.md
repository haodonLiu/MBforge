# MBForge Agent — 封存归档

封存日期：2026-06
封存时所在项目版本：v0.3.0

## 来源

原目录 `src-tauri/src/core/agent/`（22 文件，~8300 行）

## 文件清单

| 文件 | 行数 | 用途 |
|------|------|------|
| `src/arxiv.rs` | 164 | arXiv API 客户端 |
| `src/arxiv_rig.rs` | 350 | arXiv rig 工具 |
| `src/compactor.rs` | 178 | 记忆压缩 |
| `src/context.rs` | 404 | 对话上下文构建 |
| `src/conversation_store.rs` | 618 | SQLite 对话存储 |
| `src/demotion.rs` | 440 | 降级学习 |
| `src/document.rs` | 226 | 文档访问工具 |
| `src/executor_rig.rs` | 833 | 16 个 rig 工具定义 |
| `src/fs.rs` | 189 | 文件系统工具 |
| `src/kb.rs` | 44 | 知识库搜索工具 |
| `src/llm_client.rs` | 158 | LLM HTTP 客户端 |
| `src/llm_gateway.rs` | 232 | LLM 网关 |
| `src/managed_memory.rs` | 500 | 托管记忆系统 |
| `src/memory.rs` | 305 | 持久记忆（JSON 文件） |
| `src/mod.rs` | 22 | 模块声明 |
| `src/molecule.rs` | 21 | 分子分析工具 |
| `src/observability.rs` | 439 | 追踪/审计/Token 计数 |
| `src/rig_adapter.rs` | 1250 | rig-core 适配器（核心） |
| `src/rig_hooks.rs` | 347 | 审计/轨迹 Hook |
| `src/rig_memory.rs` | 308 | rig 记忆适配器 |
| `src/session_id.rs` | 109 | 会话 ID |
| `src/skills.rs` | 229 | Agent 技能管理 |
| `src/trajectory.rs` | 155 | 轨迹追踪 |

**同时封存（额外文件）：**
- `test_agent_chat.rs` — 原 `src-tauri/tests/test_agent_chat.rs`（460 行，端到端 agent 测试）
- ~~`lit_review.rs`~~ — 原 `src-tauri/src/core/document/lit_review.rs`（82 行，无调用方，已删除未保存副本）

## 提取到 tau 的类型（未封存）

| 类型 | 新位置 | 原因 |
|------|--------|------|
| `MbforgeProviderConfig` / `MbforgeProviderKind` | `core/config/llm_config.rs` | 被 `commands/llm.rs` + `parsers/structure/post_process.rs` 使用 |
| `TraceContext` / `TokenCounter` | `core/trace.rs` | 被 `core/vector/embedding.rs` 使用 |

## 解封指引

1. 创建新 Cargo 子 crate `crates/mbforge-agent/`
2. 将 `src/` 内容移入
3. 添加依赖：`rig-core`、`rig-derive`、`schemars`、`grep-regex`、`grep-searcher`、`ignore`
4. 从 tau 注入工具实现（需要 trait 改造）
