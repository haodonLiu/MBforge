# MBForge 开发规范

> 本文档集合定义架构原则、编码规范和数据表示标准。  
> 规范回答「应该是什么」；「怎么做 / 命令」见 [AGENTS.md](../../AGENTS.md)、
> [CLAUDE.md](../../CLAUDE.md)。  
> 文档总索引：[../README.md](../README.md)。

## 规范文件索引

| 文件 | 范围 | 说明 |
|------|------|------|
| [`architecture-conventions.md`](architecture-conventions.md) | 系统架构 | 五层边界、新增路由/阶段/组件约束、存储与配置 |
| [`code-style.md`](code-style.md) | 代码风格 | 命名、错误、导入、格式化原则 |
| [`molecular-representation.md`](molecular-representation.md) | 数据表示 | SMILES / E-SMILES / MoleCode 分层 |
| [`esmiles-spec.md`](esmiles-spec.md) | 数据表示 | E-SMILES 格式 |
| [`molecode-spec.md`](molecode-spec.md) | 数据表示 | MoleCode 图语法 |
| [`data-quality-phase-design.md`](data-quality-phase-design.md) | 设计 | 数据质量阶段方案（实施时对照代码） |
| [`llm-chemical-extraction-reference.md`](llm-chemical-extraction-reference.md) | 参考 | 化学抽取文献/实践笔记 |

## 与外围文档的关系

```
README.md          人类产品入口
CONTRIBUTING.md    贡献流程
AGENTS.md          AI 操作规则（短）
CLAUDE.md          AI 架构 + 命令速查
docs/specs/        本目录 — 原则与表示规范
docs/architecture/ 管线 / 错误日志等实现向参考
docs/adr/          决策记录（历史上下文 + 状态）
TODO/INDEX.md      优先级工作
```

- 改模块边界或存储布局 → 更新 `architecture-conventions.md` + 相关 ADR 状态说明 + CLAUDE/README 摘要。
- 改管线阶段 → 更新 `docs/architecture/pipeline-stages.md` 与 CLAUDE 数据流。
- 改分子表示 → 更新本目录 molecule 系列，并检查前后端契约测试。

## 规范变更流程

1. 修改本目录相关文件。
2. 同步 AGENTS.md / CLAUDE.md / README 中会误导读者的摘要（禁止三处复制大段细节）。
3. 在 PR 中写清 Why / Verify；任务状态落到 `TODO/INDEX.md` 或 Issue。
