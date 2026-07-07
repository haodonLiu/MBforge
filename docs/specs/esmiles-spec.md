# E-SMILES 规范

> 版本: 1.0 · 日期: 2026-06-04
> 基于论文: MolParser (arXiv:2411.11098)

---

## 1. 概述

E-SMILES（Extended SMILES）是标准 SMILES 的扩展，通过 XML 风格的标签表达 Markush 结构、连接点和抽象环。

**设计目标**：
- 向后兼容：SMILES 部分独立可解析（RDKit/chematic 兼容）
- 语义扩展：用标签表达 SMILES 无法表示的化学概念
- 可逆转换：与 MoleCode 无损互转

---

## 2. 顶层格式

```text
E-SMILES  :=  SMILES [ '<sep>' EXTENSION ]
EXTENSION :=  TAG [ TAG ... ]
```

- SMILES 部分必须独立可解析
- `<sep>` 仅在 EXTENSION 存在时需要
- 无 Markush 特征时，E-SMILES 退化为纯 SMILES

---

## 3. 标签类型

### 3.1 `<a>` — 原子取代基标签

```text
ATOM_TAG  :=  '<a>' INDEX ':' GROUP '</a>'
```

- **INDEX**：0 起始的原子位置（`*` 占位符的位置）
- **GROUP**：R-group 名称

```text
*c1ccccc1<sep><a>0:R[1]</a>
*CC(=O)O<sep><a>0:<dum></a>
```

### 3.2 `<r>` — 环不确定位置标签

```text
RING_TAG  :=  '<r>' INDEX ':' GROUP '</r>'
```

- **INDEX**：0 起始的环索引
- **GROUP**：R-group 名称（可带 `?n` 后缀）

```text
c1ccccc1<sep><r>0:R[1]</r><r>0:R[2]</r>
```

### 3.3 `<c>` — 抽象环标签

```text
CIRCLE_TAG :=  '<c>' INDEX ':' NAME '</c>'
```

- **INDEX**：0 起始的抽象环索引
- **NAME**：环名称（`B`=苯环, `Ar`=芳基）

```text
<sep><c>0:B</c>
```

---

## 4. GROUP 值

| 类别 | 示例 | 说明 |
|------|------|------|
| Markush R-group | `R[1]`, `R[2]` | 方括号上标 |
| 卤素占位符 | `X`, `Y`, `Z` | 通用卤素 |
| 化学缩写 | `Ph`, `Me`, `OMe`, `CF3` | 标准缩写 |
| 连接点 | `<dum>` | 悬挂键端点 |
| 自由文本 | 任意字符串 | |

---

## 5. 索引规则

- 所有索引从 0 开始
- `<a>` 标签的 INDEX 对应 `*`（dummy atom）的位置
- `<r>` 标签的 INDEX 对应环的顺序编号
- `<c>` 标签的 INDEX 对应抽象环的顺序编号
- 标签顺序无关
- 允许重复 INDEX（同一位置多个标签）

---

## 6. 示例

**单 R-group**：
```text
*c1ccccc1<sep><a>0:R[1]</a>
```

**连接点**：
```text
*C(=O)=O<sep><a>0:<dum></a>
```

**环不确定位置**：
```text
c1ccccc1<sep><r>0:R[1]</r><r>0:R[2]</r>
```

**复杂 Markush**：
```text
**C1*C(*)=C(C(*)(*)C2=CC=NC=C2)N=1<sep><a>0:R[4]</a><a>1:X</a><r>1:R[5]?n</r><a>3:Z</a><a>5:R[3]</a><a>8:R[2]</a><a>9:R[1]</a>
```

**抽象环**：
```text
********<sep><a>0:R[1]</a><a>4:R[3]</a><a>5:R[2]</a><a>7:R[5]</a><a>8:R[4]</a><c>0:B</c><a>13:R[7]</a><a>14:R[6]</a>
```

---

## 7. 三层表示

MBForge 使用三层分子表示，E-SMILES 是中间层：

| 层级 | 格式 | 存储 | 用途 |
|------|------|------|------|
| Layer 1 | SMILES | `molecules.smiles` (NOT NULL) | RDKit/chematic 兼容、指纹、子结构搜索 |
| Layer 2 | E-SMILES | `molecules.esmiles` (nullable) | 语义标签、Markush 结构 |
| Layer 3 | MoleCode | 运行时生成 | LLM 推理、Mermaid 图渲染 |

### 分离函数

`separate_esmiles_layers(raw: &str) -> (smiles, esmiles, semantic_tags)`

```text
输入: "<c>1:R1</c>CC(=O)Oc1ccccc1C(=O)O"
输出:
  smiles:       "CC(=O)Oc1ccccc1C(=O)O"
  esmiles:      "<c>1:R1</c>CC(=O)Oc1ccccc1C(=O)O"  (仅含标签时)
  semantic_tags: {"tag_1": "R1"}
```

### 转换通路

```text
SMILES ──smiles_to_esmiles()──→ E-SMILES
  │                                │
  │  parse_esmiles_tags()          │  parse_esmiles_tags()
  ↓                                ↓
SMILES ──esmiles_to_molecode()──→ MoleCode
```

- `smiles_to_esmiles(smiles, tags)` — 添加 `<sep>` + 标签
- `parse_esmiles_tags(esmiles)` — 分离 SMILES 和标签
- `esmiles_to_molecode(esmiles, name)` — 图转换为 Mermaid

---

## 8. 归一化规则

R-group 名称在存储和比较前归一化：

| 输入 | 归一化后 | 规则 |
|------|----------|------|
| `R[1]` | `R1` | 去方括号 |
| `R^1` | `R1` | 去 ^ |
| `boc` | `Boc` | 大小写归一化 |
| `OCH3` | `OMe` | 同义词映射 |
| `MeO` | `OMe` | 同义词映射 |
| `CO2H` | `COOH` | 同义词映射 |
| `Tos` | `Ts` | 同义词映射 |

详见 `abbreviation_map.rs::normalize_abbrev_name()`。

---

## 9. 实现位置

| 文件 | 功能 |
|------|------|
| `src/mbforge/chem/esmiles.py` | SMILES ↔ E-SMILES 转换 |
| `src/mbforge/parsers/molecule/chem_validate.py` | `separate_esmiles_layers()` 三层分离 |
| `src/mbforge/chem/markush.py` | E-SMILES 解析 + Markush 匹配 |
| `src/mbforge/chem/abbreviation_map.py` | 名称归一化 |
| `docs/specs/esmiles-spec.md` | 当前规范文档 |

---

## 10. 与 MoleCode 的关系

E-SMILES 和 MoleCode 是同一分子的两种表示：

| 维度 | E-SMILES | MoleCode |
|------|----------|----------|
| 格式 | SMILES + XML 标签 | Mermaid 图语法 |
| 拓扑 | 隐式（SMILES 编码） | 显式（每个键一行） |
| 标签 | `<a>N:GROUP</a>` | `{GROUP}` 缩写节点 |
| 人类可读性 | 中等 | 高（可视化） |
| LLM 友好性 | 中等 | 高（显式结构） |
| 存储 | SQLite `esmiles` 列 | 运行时生成 |

**互转**：
- E-SMILES → MoleCode：`esmiles_to_molecode()`（纯 Rust，chematic 解析）
- MoleCode → E-SMILES：需要 Mermaid 解析器（参考 `ref/MoleCode/`）
