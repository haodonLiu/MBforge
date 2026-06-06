# MBForge 任务详情

> 本文件保留原 `INDEX.md` 的任务依赖图、并行策略、Wave 划分等结构化信息。
> 任务清单摘要见 [INDEX.md](INDEX.md)；未完成项明细见 [OPEN.md](OPEN.md)。

---

## 一、任务依赖图

```
          ┌─────────────────────────────────────────────────────────┐
          │              Task A: 数据库抽象层                        │
          │  Table trait + derive macro + 迁移系统 + QueryBuilder    │
          │  难度: ★★★★☆ · 工作量: 3-4 天                           │
          └────────────────────────┬────────────────────────────────┘
                                   │ 阻塞 B
          ┌────────────────────────▼────────────────────────────────┐
          │              Task B: 分子三层迁移                        │
          │  SMILES(事实) + E-SMILES(插件) + MoleCode(推理)          │
          │  难度: ★★★☆☆ · 工作量: 2-3 天                           │
          └─────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────┐  ┌────────────────────────────────────┐
  │       Task C: 可观测性层            │  │       Task D: 管线优化              │
  │  tracing + cost + audit + budget   │  │  LLM 并行化 + Popo + 基准测试      │
  │  难度: ★★★☆☆ · 工作量: 2-3 天      │  │  难度: ★★★★☆ · 工作量: 3-5 天      │
  │  依赖: 无                          │  │  依赖: 无                          │
  └────────────────────────────────────┘  └────────────────────────────────────┘
```

Task E / F 详情见独立文档（已归档至 [archive/](archive/)）：
- [archive/2026-06-03-chematic-rust.md](archive/2026-06-03-chematic-rust.md) — Markush MoleCode 集成记录
- [E-markush-molecode.md](E-markush-molecode.md) · [F-markush-visualization.md](F-markush-visualization.md) — 任务详情

---

## 二、并行执行策略

### Wave 1（6 路并行）

- **Task A** ⬜ — 数据库抽象层（基础，阻塞 B）→ [OPEN.md O-08](OPEN.md#o-08-任务-a数据库抽象层)
- **Task C** ⬜ — 可观测性层（独立）→ [OPEN.md O-09](OPEN.md#o-09-任务-c可观测性层)
- **Task D** 🟧 — 管线优化（独立）
- **Task E** ✅ — 见 [E-markush-molecode.md](E-markush-molecode.md)
- **Task F** ✅ — 见 [F-markush-visualization.md](F-markush-visualization.md)

### 部分完成

- **Task B** 🟧 — 详见 [OPEN.md O-10](OPEN.md#o-10-任务-b-收尾fts5-重建--sanitize_esmiles-清理)
- **Task D** 🟧 — `index_project_rust` 已用 `buffer_unordered(4)` 并行化（`pipeline.rs:1227`）；LLM 后处理仍串行

### Wave 2（A 完成后）

- **Task B 收尾**（依赖 A 的 Table trait）

---

## 三、任务详情

### Task A — 数据库抽象层 ⬜
- Table trait + derive macro + 迁移系统 + QueryBuilder
- **状态**：0 进展（grep `trait Table` 0 命中）
- **详情**：[OPEN.md O-08](OPEN.md#o-08-任务-a数据库抽象层)

### Task B — 分子三层迁移 🟧
- Layer 1: SMILES（`molecules.smiles NOT NULL`）✅
- Layer 2: E-SMILES（`molecules.esmiles` nullable）✅
- Layer 3: MoleCode（运行时生成）— `core/molecode.rs` ✅
- **未完成**：FTS5 重建 + `sanitize_esmiles` 清理
- **详情**：[OPEN.md O-10](OPEN.md#o-10-任务-b-收尾fts5-重建--sanitize_esmiles-清理)

### Task C — 可观测性层 ⬜
- tracing + cost + audit + budget
- **详情**：[OPEN.md O-09](OPEN.md#o-09-任务-c可观测性层)

### Task D — 管线优化 🟧
- PDF 解析+分子提取：`buffer_unordered(4)` ✅
- LLM 后处理：仍串行
- 写库阶段（SQLite）：显式串行（合理）

### Task E — Markush MoleCode ✅
- 见 [E-markush-molecode.md](E-markush-molecode.md)

### Task F — Markush 可视化 ✅
- 见 [F-markush-visualization.md](F-markush-visualization.md)

### Task G — 分子交互式编辑 ✅
- Ketcher + `MoleculeDetailPanel` + 理化性质
- 落地：`frontend/src/components/molecule/MoleculeEditorDialog.tsx`

### Task H — 置信度与校对 ⬜（部分看板错标见 archive）
- 阈值过滤（滑块）— [O-01](OPEN.md#o-01-置信度阈值过滤滑块前端-ui)
- 低置信度提醒 — [O-02](OPEN.md#o-02-低置信度项目级全局提醒)
- SMILES 验证兜底（标红）— [O-03](OPEN.md#o-03-smiles-无效标红--编辑提示前端-ui)
- 分子状态标记 — 已实现（看板错标，详见 [archive/sync-偏差-2026-06-06.md](archive/sync-偏差-2026-06-06.md)）
- 区域重新检测 — [O-04](OPEN.md#o-04-区域重新检测迁到-tauri-invoke)

---

## 四、共享规范

所有任务遵循 [STANDARDS.md](STANDARDS.md)。

---

> **维护规则**：
> 1. 任务状态变化 → 先改 [OPEN.md](OPEN.md) 对应条目 → 再改本文件
> 2. ✅ 任务不再展开详情（保留跳转 + 归档链接）
> 3. 季度回顾：评估每个任务是否仍适用
