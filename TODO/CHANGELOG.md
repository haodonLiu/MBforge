# MBForge 项目工作变更记录（精简版）

> 本文件只保留**当前进行中**的变更与**指向 archive/ 的指针**。
> 已完成的修复包、git log 快照、看板偏差核验详见 [archive/](archive/)。

---

## 进行中

### 2026-06-06 — O-05 完成（Agent audit hook M6 接入）
- `commands/agent.rs:593-606` `build_mbforge_agent` 签名加 `Option<ConcreteHook>` 参数
- 调用点 L540-550 组合 `audit_hook` + `trajectory_hook` 为项目级 `ConcreteHook` 传入
- audit 创建失败或无 project_root 时传 None → fallback 到临时 hook（向后兼容）
- 真实修复：`build_mbforge_agent` 不再用 `tempfile::tempdir()` 临时 audit，session 内的 LLM 循环现在写到项目根的 `.mbforge/audit.jsonl`
- `cargo test --lib rig` 13/13 passed
- 同步修正 OPEN.md / INLINE-TODOS.md 描述与代码对齐（O-04/O-07 描述失实已改）
### 2026-06-06 — O-02 完成（项目级低置信度提醒）
- 新增 `frontend/src/components/molecule/LowConfidenceBanner.tsx`：项目级低置信度汇总组件
- `MoleculeReviewPanel` 顶部插入 banner，复用 O-01 `useConfidenceThreshold` 阈值
- 替换 L81 硬编码 0.6 → threshold（与 O-01 自动确认门槛同一份）
- 仅统计 `status='pending' & confidence < threshold` 的分子（已 accept/reject 不重复提醒）
  - total === 0 时不渲染
  - total > 5 时显示"+N 更多"展开按钮
  - 点击分子项触发 `onSelect(moleculeId)`（可选跳转）
- **用户自发修复 Workflow.tsx**（与 502 诊断相关）：3 处 `r.ok` 检查 + `showToast('Python sidecar 未启动')` 提示
- `tsc --noEmit` 无 O-02 引入回归（剩 SAR pre-existing 1 个 + Workflow.tsx 用户修改 3 个 unused e）
### 2026-06-06 — O-10 完成（Task B 收尾）
- `pipeline.rs:888-898` 删冗余 sanitize 循环（紧跟 `validate_smiles_batch` 入口净化）
- 决定保留：`post_process.rs:669`（早期净化让日志输出一致）、`chem_validate.rs:27/90`（公共 API 入口净化）
- FTS5 schema **不改造**：当前独立 fts_conn + 显式同步是合理设计，OPEN.md 旧描述失实
- `cargo test --lib pipeline::` 15/15 passed
### 2026-06-06 — O-01 + O-03 完成
- 置信度阈值滑块（O-01）→ `ConfidenceThresholdSlider` + `useConfidenceThreshold` hook + `Slider` UI
- 阈值接入 `CorrectionPanel.handleFinish` 决定自动确认/拒绝
- 持久化到 `localStorage['mbforge_confidence_threshold']`（默认 0.5）
- SMILES 标红（O-03）→ `MoleculeDisplay` 接 `validateSmiles` 防抖校验
- 错误暴露：`validateSmiles` 失败时不再静默，把 `error` 提升为 `ValidationIssue`
- MoleculeDisplay: 外层边框 + input 边框 + SMILES 文本框 + 静态占位 四处标红

### 2026-06-06 — 502 错误诊断（Workflow.tsx Environment 页）
- **症状**：`GET /api/v1/environment/check` / `download/models` / `download/model-paths` 返 502
- **根因**：Python sidecar (uvicorn :18792) 未运行 — `127.0.0.1:18792` 连接被拒
- **影响**：仅 Environment 页异常，O-01/O-03 不依赖 sidecar（走 `chem_validate_smiles` Tauri invoke）
- **修复**（不修代码）：手动启动 sidecar `cd src/mbforge && uv run python -m mbforge.model_server`
- **代码加固建议**（未做）：Workflow.tsx 三处 `r.json()` 缺 `r.ok` 检查，sidecar 缺失时会丢 SyntaxError。可作为 P3 健壮性改进。

### 2026-06-06 — 快速胜利包 ✅
 完成 [OPEN.md O-14](OPEN.md) + O-23，归档至 [archive/2026-06-06-quick-wins.md](archive/2026-06-06-quick-wins.md)

---

## 变更指针

| 日期 | 主题 | 详情 |
|------|------|------|
| 2026-06-06 | 任务管理集中化重构 + 散落待办扫描 | 本轮变更（详情见下） |
| 2026-06-06 | 看板偏差核验 | [archive/sync-偏差-2026-06-06.md](archive/sync-偏差-2026-06-06.md) |
| 2026-06-04 | 一次性修复包（13 类） | [archive/2026-06-04-fix-bundle.md](archive/2026-06-04-fix-bundle.md) |
| 2026-06-04 | 提交记录快照（16 commits） | [archive/git-log-snapshot.md](archive/git-log-snapshot.md) |
| 2026-06-03 | 化学信息学 Rust 化 + schematic 集成 | [archive/2026-06-03-chematic-rust.md](archive/2026-06-03-chematic-rust.md) |

---

## 2026-06-06 — 任务管理集中化（本轮）

### 起因
- `TODO/INDEX.md` 看板与代码实际状态有偏差（如 SAR Rust 化、分子状态标记实际已实现）
- 代码内 4 处 `TODO`/`占位` 注释散落在 `src-tauri/src`、`src/mbforge/` 多个文件
- `AGENTS.md` §技术债务 #1-#8 描述与代码现状部分不符（如 #4 已修未更新）
- 缺乏"代码内待办"统一登记

### 行动
1. 全文 ripgrep 扫描 + 上下文核验，建立**真实状态**而非看板声称
2. 重组 `TODO/` 目录为"唯一入口 + 分类明细"结构（详见 [INDEX.md](INDEX.md) §一）
3. 删除原 `TODO.md`（内容已分发到新文件 + archive/）
4. 同步偏差：识别 4 处看板错标/漏报（已归档到 archive/）

### 同日跟进（2026-06-06 下午）
- **完成**：已完成项归档到 `archive/`，主文件瘦身
  - 4 个文件移走（fix-bundle / chematic-rust / git-log / sync-偏差）
  - 净减主文件 ~10 KB
- **维护规则更新**：见 [INDEX.md](INDEX.md) §六 + 各文件末尾
