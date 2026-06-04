# MBForge 开发规范

> 本文档集合定义项目的架构原则、编码规范和数据表示标准。
> 规范不含具体代码实现，只规定概念、约束和要求。

## 规范文件索引

| 文件 | 范围 | 说明 |
|------|------|------|
| [`molecular-representation.md`](molecular-representation.md) | 数据表示 | 分子存储的三层格式规范（SMILES / E-SMILES / MoleCode） |
| [`architecture-conventions.md`](architecture-conventions.md) | 系统架构 | 模块边界、分层职责、状态管理约定 |
| [`code-style.md`](code-style.md) | 代码风格 | 命名、注释、错误处理的高层原则 |

## 与外围文档的关系

```
AGENTS.md ──────────────┐
  (完整工作规范)         │
                        ├──▶ docs/specs/ ◀──── 本文档集（高层原则）
CLAUDE.md ──────────────┤      │
  (快速参考)            │      ▼
                        │   CODEMAP.md §规范引用
CODEMAP.md ─────────────┘   (代码逻辑树中的约束标记)
```

- **AGENTS.md**：面向 Agent 的完整工作规范（含具体命令、文件路径、构建步骤）。
- **CLAUDE.md**：面向 Claude Code 的快速参考（架构图、关键文件、常用命令）。
- **CODEMAP.md**：代码逻辑树，在相关模块处引用本规范集的约束条款。
- **docs/specs/**：本规范集，只回答"应该是什么"，不回答"怎么做"。

## 规范变更流程

1. 修改本规范集内的文件。
2. 在 `CODEMAP.md` §7.6 记录待审核项。
3. 同步更新 AGENTS.md / CLAUDE.md 中的引用链接（如有新增规范文件）。
