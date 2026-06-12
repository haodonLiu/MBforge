# MBForge 任务看板

## P0 — 正在进行 / 阻塞

## P1 — 近期计划

- [ ] **处理队列 UX 优化 + 当前 PDF 流程图**（2026-06-12）
      见 `TODO/2026-06-12-processing-queue-ux.md`。
      Phase 1+2：A PdfPipelineFlow · B 列表打磨 · C 吞吐洞察 · G 跨页 toast。

## P2 — 中期计划

## P2 — 中期计划

## 技术债务

> 与 `AGENTS.md`「技术债务」同步维护。修复后两边同时更新。

| # | 债务 | 严重性 | 状态 | 修复方案 | 优先级 |
|---|------|--------|------|---------|--------|
| 1 | chem_validate.rs 与 core/chem.rs 重叠 | 中 | 🟥 待修复 | 合并到 chem.rs | P2 |
| 2 | vector_store.rs 接口臃肿 | 低 | 🟥 待修复 | 合并到 sqlite_vector_store.rs | P3 |
| 3 | 多个 std::sync::Mutex 在 async 上下文 | 高 | 🟧 进行中 | 迁移到 tokio::sync::Mutex | P1 |
| 4 | chematic git 依赖缺 tag | 中 | 🟥 待修复 | 锁定到特定 commit | P2 |
| 5 | Python sidecar 单进程无连接池 | 中 | 🟥 待修复 | 添加连接池 + 优雅降级 | P2 |
| 6 | tracing 覆盖不全 | 中 | 🟧 部分完成 | 扩展 observability.rs 到所有跨边界调用 | P2 |
| 7 | 无成本护栏 | 中 | 🟥 待修复 | 新增 BudgetEnforcer | P3 |
| 8 | 27 分钟管线瓶颈 | 高 | 🟧 部分完成 | LLM 调用并行化 | P1 |
| 9 | constants.rs 生成机制失效 | 中 | 🟧 部分完成 | 脚本已修复，Rust 侧改为参考文件 + 人工合并 | P2 |

---

## P3 — 远期 / 想法

## 已完成（本次会话）

- [x] 前端 API 彻底统一到单层（`api/tauri/*`）
- [x] Environment 页面添加"刷新模型环境"按钮（调用 `refresh_resolved_paths` + 自动重载模型列表）
- [x] 删除遗留顶层 API 文件（`http.ts`、`download.ts`、`moldet.ts`、`settings.ts`）
- [x] Rust/Python 模型路径扫描统一为 ENV 优先级顺序（MBFORGE → HF_HOME → MODELSCOPE → TORCH_HOME）
- [x] Python 侧改为优先读 Rust 写入的 `resolved_paths.json`（单一真相源）
- [x] Rust 添加 `refresh_resolved_paths` Tauri 命令供前端刷新调用
- [x] `resolved_paths.json` 缓存改为 mtime 感知，Rust 刷新后 Python 自动重读
