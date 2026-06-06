# MBForge 任务总索引

> 最后更新: 2026-06-04

---

## 任务依赖图

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

  ┌────────────────────────────────────┐  ┌────────────────────────────────────┐
  │       Task E: Markush MoleCode     │  │       Task F: Markush 可视化        │
  │  缩写展开 + 归一化 + Kekule 等价   │  │  mermaid.js + Tauri 命令 + 组件     │
  │  难度: ★★★☆☆ · 工作量: 2-3 天      │  │  难度: ★★★☆☆ · 工作量: 2-3 天      │
  │  依赖: 无                          │  │  依赖: 无                          │
  └────────────────────────────────────┘  └────────────────────────────────────┘
```

---

## 任务清单

| ID | 名称 | 难度 | 工作量 | 依赖 | 状态 | 文件 |
**🔴 P0（用户明显感知）**：[O-04](OPEN.md#o-04-moldet-区域重检设计分离) · [O-06](OPEN.md#o-06-代码内占位--2--embedding-替换为-onnx-runtime) · O-05 归档
| A | 数据库抽象层 | ★★★★☆ | 3-4 天 | 无 | ⬜ | [A-database-layer.md](A-database-layer.md) |
| B | 分子三层迁移 | ★★★☆☆ | 2-3 天 | A | ✅ 已完成 | [B-molecule-three-layer.md](B-molecule-three-layer.md) |
| C | 可观测性层 | ★★★☆☆ | 2-3 天 | 无 | ⬜ | [C-observability.md](C-observability.md) |
| D | 管线优化 | ★★★★☆ | 3-5 天 | 无 | 🟧 部分完成 | [D-pipeline-optimization.md](D-pipeline-optimization.md) |
| E | Markush MoleCode 增强 | ★★★☆☆ | 2-3 天 | 无 | ✅ 已完成 | [E-markush-molecode.md](E-markush-molecode.md) |
| F | Markush 可视化 | ★★★☆☆ | 2-3 天 | 无 | ✅ 已完成 | [F-markush-visualization.md](F-markush-visualization.md) |
| G | 分子交互式编辑 | ★★★☆☆ | 1-2 天 | 无 | ✅ 已完成 | Ketcher + MoleculeDetailPanel |
| H | 置信度与校对增强 | ★★★☆☆ | 2-3 天 | 无 | 🟧 部分完成 | 阈值过滤(O-01✅) + SMILES 标红(O-03✅) + 低置信度提醒(O-02✅) + 区域重检(O-04) |

---

## 并行执行策略

### Wave 1（立即启动，6 路并行）

- **Task A** — 数据库抽象层（基础，阻塞 B）
- **Task C** — 可观测性层（独立）
- **Task D** — 管线优化（独立）
- **Task E** — Markush MoleCode 增强（独立）✅ 已完成
- **Task F** — Markush 可视化（独立）

### 已完成的部分

- **Task B ✅ 完成**（2026-06-06）：SMILES（事实）+ E-SMILES（标签）+ MoleCode（图）三层架构 + `chem_validate.rs` 净化清理（O-10）
- **Task D 部分**: `index_project_rust` 已用 `buffer_unordered(4)` 并行化。LLM 串行瓶颈未完成。
- **Task E**: 缩写展开映射表 + 名称归一化 + check_overlap 增强 已完成。

### Wave 2（A 完成后）
- **Task B** — 分子三层迁移（依赖 A 的 Table trait）

---

 ## 共享规范

所有任务遵循 `TODO/STANDARDS.md` 中定义的开发规范。

---

## 架构参考

| 文档 | 说明 |
|------|------|
| `ARCHITECTURE.md` | 目标架构设计 |
| `ref/INDEX.md` | 参考资料索引 |
| `AUDIT.md` | 项目审计报告 |
| `CODEMAP.md` | 代码逻辑树 |
