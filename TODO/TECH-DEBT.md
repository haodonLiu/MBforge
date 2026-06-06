# MBForge 技术债务与风险清单

> 本文件是**当前活跃**的技术债务与风险。已修复/已归档的项见 [archive/](archive/)。
> 核验方式：ripgrep + cargo + 文件存在性。

---

## 一、活跃技术债务（7 条）

| # | 描述 | 核验 | 建议工作量 |
|---|------|------|-----------|
| 1 | `chem_validate.rs` 与 `core/chem/chem.rs` 功能重叠 | rg `chem_validate` 9 文件命中 | 2-3 天 |
| 2 | ~~旧 `vector_store.rs` 被 `sqlite_vector_store.rs` 取代但未删除~~ | ✅ 已修（2026-06-06，SearchResult 合并入 sqlite_vector_store.rs）| — |
| 3 | 6 个文件仍用 `std::sync::Mutex` 在 async 上下文 | `sqlite_vector_store.rs` / `semantic_cache.rs` / `ingest_queue.rs` / `file_cache.rs` / `molecule_db.rs` / `content_cache.rs` | 1 周（需并发测试） |
| 5 | Python sidecar 无连接池 | rg `httpx\.AsyncClient|requests\.Session` → 0 命中 | 1 周 |
| 6 | 无结构化 tracing | rg `tracing::|tracing_subscriber` → 0 命中 | 1 天（基础设施）|
| 7 | 无 BudgetEnforcer | 仅 1 行注释在 `observability.rs`（"已显式移出"）| 合并到 [OPEN.md O-09](OPEN.md#o-09-任务-c可观测性层) |
| 8 | 27 分钟管线瓶颈（LLM 串行） | PDF 解析+分子提取已 `buffer_unordered(4)`（`pipeline.rs:1227`）；LLM 后处理仍串行 | 1-2 周 |

> **#4 chematic git 依赖无 tag** 已于 2026-06-04 修复（`Cargo.toml:46-50` 锁到 `rev = "2702636"`），从活跃列表移除。详见 [archive/2026-06-03-chematic-rust.md](archive/2026-06-03-chematic-rust.md)。

---

## 二、风险清单

| 风险 | 状态 | 缓解 |
|------|------|------|
| chematic 被删/改 API | ✅ 已缓解 | commit 锁定 + 响应式解析器 |
| Python sidecar 崩溃 | ❌ 未缓解 | 见债务 #5 |
| Tauri v3 破坏性变更 | 关注即可 | 关注迁移指南 |
| Python 依赖腐化 | ✅ 已缓解 | uv.lock 锁定 |
| 管线瓶颈 | ⚠️ 部分缓解 | 见债务 #8 |
| SQLite Windows 文件锁 | ❌ 未缓解 | TODO/TODO.md §三 列出 |
| 跨语言常量/Config 重复 | ⚠️ 部分缓解 | `scripts/generate_constants.py` 存在 |

---

## 三、AGENTS.md 同步建议

下列描述已与代码现状不符，**建议下季度更新 AGENTS.md**：

1. **§技术债务 #4** 已修，移到历史
2. **§技术债务 #6 / #7** 与 OPEN.md O-09 重叠，建议合并描述
3. **§技术债务 #8** 原文未注明已缓解部分，更新为"PDF 解析层已并行；LLM 后处理仍串行"

---

## 四、修复优先级（按 ROI）

| ROI | 项 | 预估 |
|-----|----|------|
| 🟢 极高 | #2 删旧 vector_store.rs | 1 小时 |
| 🟢 极高 | #6 tracing 初始化层 | 1 天 |
| 🟡 中 | #1 合并 chem_validate.rs | 2-3 天 |
| 🟡 中 | #8 LLM 后处理并行化 | 1-2 周 |
| 🟡 中 | #5 Python 连接池 + 健康检查 | 1 周 |
| 🔴 高风险 | #3 迁 Mutex | 1 周 |
| 🔴 高风险 | #7 BudgetEnforcer | 合并到 O-09 |

---

> **维护规则**：
> 1. AGENTS.md §技术债务 摘要与本文件保持一致
> 2. 修复后从本表移除，归档到 [archive/](archive/)（按日期分类）
> 3. 季度回顾：评估每条是否仍适用
