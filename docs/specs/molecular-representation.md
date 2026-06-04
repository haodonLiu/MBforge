# 分子表示规范

> 版本: 0.1.0 | 日期: 2026-06-04
> 规定 MBForge 中分子结构的存储、交换和推理表示标准。

## 核心原则

**分层单一来源**：SMILES 是唯一持久化存储格式。MoleCode 是运行时推理视图。E-SMILES 是可选语义插件。

## 三层架构

```
┌────────────────────────────────────────┐
│  Layer 3: MoleCode（Agent 交互层）      │
│  作用: LLM 可见的显式图表示              │
│  生命周期: 运行时临时生成，不持久化       │
│  来源: SMILES → molecode 转换器         │
└────────────────────────────────────────┘
                    ▲
                    │ 双向转换（调用 sidecar）
                    ▼
┌────────────────────────────────────────┐
│  Layer 2: E-SMILES（语义插件层）        │
│  作用: SMILES 的语义扩展                 │
│  格式: SMILES + MBForge 标签             │
│  生命周期: 可选，数据库 nullable         │
│  约束: 标签必须可解析分离为纯 SMILES     │
└────────────────────────────────────────┘
                    ▲
                    │ 解析（去掉标签）
                    ▼
┌────────────────────────────────────────┐
│  Layer 1: SMILES（事实来源层）          │
│  作用: 唯一持久化标准格式                │
│  约束: 必须能被 RDKit MolFromSmiles 解析 │
│  生命周期: 数据库 NOT NULL，永久存储     │
└────────────────────────────────────────┘
```

## 各层职责与约束

### Layer 1: SMILES（事实来源）

| 项 | 规定 |
|---|---|
| 存储 | 数据库 `smiles TEXT NOT NULL` 为主字段 |
| 搜索 | FTS5 索引 `smiles` 列（不含标签噪音） |
| 计算 | RDKit / chematic 直接输入，无需预处理 |
| 交换 | 与外部数据库（PubChem、ChEMBL）交换的唯一格式 |
| 规范 | 必须产生有效的 RDKit Mol 对象 |

### Layer 2: E-SMILES（语义插件）

| 项 | 规定 |
|---|---|
| 可选性 | 数据库 `esmiles TEXT` 可为 NULL |
| 语义 | 标签仅用于 Markush R-group 位置、提取来源、置信度等元数据 |
| 可分离 | 必须能从 E-SMILES 解析出纯净 SMILES（标签剥离后即为 Layer 1） |
| 附加数据 | 复杂元数据优先存入 `tags JSON` 字段，而非嵌入 E-SMILES 字符串 |

### Layer 3: MoleCode（推理视图）

| 项 | 规定 |
|---|---|
| 非持久 | 不存入数据库，运行时按需转换 |
| 用途 | Agent 分子编辑、Markush 分析、合成路线推理 |
| 转换 | 通过 Python sidecar `/api/v1/molecode/convert` 双向转换 |
| 验证 | MoleCode → SMILES 转换后必须通过 RDKit 验证 |

## 跨层操作规则

### 存储流程

```
提取原始文本
    │
    ├── 若是 E-SMILES → 分离为 (smiles, tags) → 分别存入 Layer 1 和 tags JSON
    │
    └── 若是纯 SMILES → 直接存入 Layer 1，esmiles/tags 留空
```

### Agent 推理流程

```
从数据库读取 smiles
    │
    ▼
smiles → molecode（sidecar 转换）
    │
    ▼
LLM 在 MoleCode 上推理/编辑
    │
    ▼
编辑后的 molecode → smiles（sidecar 转换）
    │
    ▼
RDKit 验证 → 存入数据库
```

### 禁止事项

- 禁止以 E-SMILES 作为 RDKit / chematic 的输入（必须先剥离标签）。
- 禁止将 MoleCode 直接存入数据库或 FTS5 索引。
- 禁止在 SMILES 主字段中混入任何非标准字符（标签、注释、markdown）。

## 迁移状态

| 项 | 当前状态 | 目标状态 |
|---|---|---|
| 数据库主字段 | `esmiles TEXT NOT NULL` | `smiles TEXT NOT NULL` + `esmiles TEXT` + `tags TEXT` |
| FTS5 索引 | 索引 `esmiles` | 索引 `smiles` |
| RDKit 调用 | 先 `sanitize_esmiles()` 再解析 | 直接使用 `smiles` |
| Agent 工具 | 直接读 E-SMILES | 读 `smiles` → 转 MoleCode → 推理 |
