# E-SMILES (Extended SMILES) — MBForge 集成规范

> 基础规范来源: arXiv:2411.11098 — MolParser §3.1
> MBForge 特化: Rust 管道集成、MoleculeDatabase 存储、PDF 提取通路适配
> Date: 2026-05-30

## 概述

E-SMILES (Extended SMILES) 在标准 SMILES 基础上通过 XML 风格扩展标签表达 Markush 结构、连接点和抽象环。
MBForge PDF 管道中，分子提取可能产出带 E-SMILES 特征的结构（尤其专利文档），需要 Rust 侧解析、存储和查询。

---

## 1. 格式总览

```
SMILES<sep>EXTENSION
```

| 组成部分 | 必需 | 说明 |
|---------|------|------|
| `SMILES` | 是 | 标准 RDKit 兼容 SMILES |
| `<sep>` | 条件必需 | 仅 EXTENSION 存在时 |
| `EXTENSION` | 否 | XML 风格标签 |

---

## 2. 标签类型

| 标签 | 形式 | 含义 |
|------|------|------|
| `<a>` | `<a>ATOM_INDEX:GROUP</a>` | 原子上 R 基团/缩写/连接点 |
| `<r>` | `<r>RING_INDEX:GROUP</r>` | 环上不确定位置连接 |
| `<c>` | `<c>CIRCLE_INDEX:NAME</c>` | 抽象环（B, Ar） |
| `<dum>` | `<a>ATOM_INDEX:<dum></a>` | 连接点（开放键端） |

**GROUP_NAME 取值**: `R[n]`, `X`, `Y`, `Z`, `Ph`, `Me`, `OMe`, `Et`, `Pr`, `Bu`, `CF3`, `<dum>`, 或任意字符串。

---

## 3. MBForge Rust 实现

### 3.1 E-SMILES 数据模型

```rust
/// E-SMILES 解析结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExtendedSmiles {
    /// 标准 SMILES 部分（不含扩展）
    pub core_smiles: String,
    /// 原始完整字符串
    pub raw: String,
    /// 原子取代基标签 <a>
    pub atom_tags: Vec<SubstituentTag>,
    /// 环不确定连接标签 <r>
    pub ring_tags: Vec<SubstituentTag>,
    /// 抽象环标签 <c>
    pub circle_tags: Vec<CircleTag>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubstituentTag {
    pub index: u32,
    pub group: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CircleTag {
    pub index: u32,
    pub name: String,
}
```

### 3.2 解析器

```rust
use regex::Regex;

lazy_static! {
    static ref ATOM_RE: Regex = Regex::new(r"<a>(\d+):([^<]+)</a>").unwrap();
    static ref RING_RE: Regex = Regex::new(r"<r>(\d+):([^<]+)</r>").unwrap();
    static ref CIRCLE_RE: Regex = Regex::new(r"<c>(\d+):([^<]+)</c>").unwrap();
}

/// 解析 E-SMILES 字符串。
/// 如果无 `<sep>` 则退化为纯 SMILES。
pub fn parse_esmiles(input: &str) -> ExtendedSmiles {
    let (core_smiles, ext) = match input.split_once("<sep>") {
        Some((s, e)) => (s.to_string(), Some(e)),
        None => (input.to_string(), None),
    };

    let mut result = ExtendedSmiles {
        core_smiles: core_smiles.clone(),
        raw: input.to_string(),
        atom_tags: Vec::new(),
        ring_tags: Vec::new(),
        circle_tags: Vec::new(),
    };

    let ext = match ext {
        Some(e) => e,
        None => return result,
    };

    for cap in ATOM_RE.captures_iter(ext) {
        result.atom_tags.push(SubstituentTag {
            index: cap[1].parse().unwrap_or(0),
            group: cap[2].to_string(),
        });
    }

    for cap in RING_RE.captures_iter(ext) {
        result.ring_tags.push(SubstituentTag {
            index: cap[1].parse().unwrap_or(0),
            group: cap[2].to_string(),
        });
    }

    for cap in CIRCLE_RE.captures_iter(ext) {
        result.circle_tags.push(CircleTag {
            index: cap[1].parse().unwrap_or(0),
            name: cap[2].to_string(),
        });
    }

    result
}

/// 提取核心 SMILES（用于 substructure search / fingerprint）。
pub fn core_smiles(input: &str) -> &str {
    input.split_once("<sep>").map_or(input, |(s, _)| s)
}

/// 判断是否为 E-SMILES（含扩展标签）。
pub fn is_extended(input: &str) -> bool {
    input.contains("<sep>")
}
```

### 3.3 与 MoleculeDatabase 集成

MoleculeDatabase 的 `MoleculeRecord.smiles` 字段存储完整 E-SMILES 字符串（含 `<sep>` + EXTENSION）。
核心 SMILES 用于 FTS5 索引和去重；EXTENSION 存为 metadata 的 `esmiles_extension` 字段。

```
MoleculeRecord {
    mol_id: String,
    smiles: String,           // 完整 E-SMILES
    molecular_weight: f64,    // 仅基于 core_smiles 计算
    metadata: serde_json::Value,
    status: String,
    source_doc: String,
    page: u32,
}
```

```rust
impl MoleculeDatabase {
    pub fn add_esmiles(&self, input: &str, doc_id: &str, page: u32) -> Result<(), String> {
        let es = parse_esmiles(input);
        let core = core_smiles(input);

        let record = MoleculeRecord {
            mol_id: generate_uuid(),
            smiles: input.to_string(),         // 完整 E-SMILES
            molecular_weight: estimate_molecular_weight(core),
            metadata: serde_json::json!({
                "esmiles_extension": {
                    "atom_tags": es.atom_tags,
                    "ring_tags": es.ring_tags,
                    "circle_tags": es.circle_tags,
                }
            }),
            status: if es.atom_tags.is_empty() && es.ring_tags.is_empty() {
                "defined".to_string()
            } else {
                "markush".to_string()
            },
            source_doc: doc_id.to_string(),
            page,
        };

        self.add_molecule(&record)
    }
}
```

---

## 4. PDF 管道中的 E-SMILES 处理

### 4.1 提取通路

PDF 文本 → SMILES/分子名提取 → E-SMILES 识别 → 解析 → 存入 MoleculeDatabase

### 4.2 关联逻辑（association.rs）

`commands/extractor.rs` 的 `extract_associated_molecules` 已按 200-char 窗口关联 SMILES 与活性数据。
E-SMILES 完整字符串参与关联，存储时 core_smiles 用于去重：

```rust
pub fn extract_associated_molecules(text: &str) -> Vec<(String, Vec<ActivityEntry>)> {
    // ... 现有 SMILES 提取逻辑 ...
    // 提取到的 SMILES 可能包含 E-SMILES（含 <sep> 的字符串）
    // 去重时仅比较 core_smiles 部分
}
```

### 4.3 去重规则（molecule_dedup.rs）

| 场景 | 去重依据 | 说明 |
|------|---------|------|
| 无 EXTENSION | 完整 SMILES | 标准 SMILES 去重 |
| 有 EXTENSION | core_smiles | 同一核心结构视为重复，保留首个 |

---

## 5. 搜索与查询

### 5.1 FTS5 全文搜索

MoleculeDatabase 的 FTS5 索引 `mol_fts` 包含 `smiles` 列。
E-SMILES 全文存入 FTS5，支持 `<a>0:R[1]</a>` 等字符串搜索。

### 5.2 状态过滤

`status` 字段区分 `"defined"`（标准分子）和 `"markush"`（含 Markush 特征）：

```rust
// 仅查询已定义分子
let defined = db.list_all(Some(100), Some(0), Some("defined"))?;

// 仅查询 Markush 结构
let markush = db.list_all(Some(100), Some(0), Some("markush"))?;
```

---

## 6. 示例

### 6.1 解析单 R 基团

```rust
let es = parse_esmiles("*c1ccccc1<sep><a>0:R[1]</a>");
assert_eq!(es.core_smiles, "*c1ccccc1");
assert_eq!(es.atom_tags[0].group, "R[1]");
```

### 6.2 退化为标准 SMILES

```rust
let es = parse_esmiles("CC(=O)O");
assert_eq!(es.core_smiles, "CC(=O)O");
assert!(es.atom_tags.is_empty());
assert!(!is_extended("CC(=O)O"));
```

### 6.3 环不确定连接

```rust
let es = parse_esmiles("c1ccccc1<sep><r>0:R[1]</r>");
assert_eq!(es.ring_tags[0].group, "R[1]");
assert_eq!(es.ring_tags[0].index, 0);
```

---

## 7. 注意事项

| 事项 | 说明 |
|------|------|
| RDKit 兼容 | MBForge 当前无 RDKit 依赖；core_smiles 仅用于 fingerprint 生成（Python sidecar） |
| 索引计数 | 原子索引从 0 开始（Rust 习惯），与论文规范一致 |
| `<sep>` 分隔 | Rust 中直接用 `str::split_once("<sep>")` 解析 |
| 空 EXTENSION | 无 EXTENSION 时 `<sep>` 也省略，退化为纯 SMILES |
| 存储开销 | 完整 E-SMILES 存入 `smiles` 字段，EXTENSION 重复复制到 `metadata.esmiles_extension` 以便快速过滤 |
