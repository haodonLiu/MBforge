# Pipeline 增量改造 + 分子关系层设计

> 日期：2026-05-30
> 状态：设计完成，待实现

---

## 1. 背景与问题

### 1.1 当前 Pipeline 的问题

| 问题 | 现状 | 影响 |
|------|------|------|
| 用户意图不区分 | "只提取 TABLE 1" 和 "提取全部" 结果一样 | 浪费 LLM token，结果噪音大 |
| 无图片通道 | `extract_smiles_candidates` 是纯文本正则 | 化学结构图中的分子完全丢失 |
| 一次性处理 300KB | `post_process` 把全部 content 分批喂 LLM | 精度下降，上下文溢出 |
| 正则假阳性 | SMILES 正则匹配非化学字符串 | 污染 LLM 输入，产生错误数据 |
| chat agent 与 processing 混淆 | `agent.rs` 的 ReAct 循环不适合文件处理 | 架构混乱 |

### 1.2 设计决策

**不新建 DocAgent**，扩展现有 `pipeline.rs` + `post_process.rs`：

- Pipeline 是确定性编排（extraction → classification → chunking → molecule extraction → post_process），不需要 ReAct 循环
- 如果 Stage 2 需要"LLM 判断 section 是否包含活性数据然后决定是否提取"，这才需要 Agent——但现有 pipeline 没有这个需求
- 真正需要的是：**intent routing**（用户意图路由）和 **VLM 化学结构识别**

---

## 2. 流水线设计

```
用户: "提取 TABLE 1 中所有活性数据"
        │
        ▼
┌─ Stage 0: 文件分类 ──────────────────────────────────────┐
│  pdf_path → pdf-inspector classify                        │
│  if scanned → mineru_extract(path) → text + images[]      │
│  if text    → pdf-inspector extract_text → text           │
│  结果存入 DocProcessingContext                            │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌─ Stage 1: 快速结构分析 ───────────────────────────────────┐
│  读 raw_text 的前 8000 字符                                │
│  → LLM meta prompt 输出 JSON 结构描述                      │
│  结果: DocStructure { doc_type, sections[], has_images }   │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌─ Stage 1.5: 用户意图路由 ─────────────────────────────────┐
│  interpret_request(&structure, user_request)               │
│  → 只处理 "TABLE 1"/"results"/"biological" section         │
│  → 只提取化合物 + 活性数据（跳过合成方法、制剂）            │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌─ Stage 2: 逐 section 处理 ────────────────────────────────┐
│  for section in plan.target_sections:                      │
│    ├─ extract_section(&raw_text, &boundary)                │
│    ├─ if section 有配图:                                    │
│    │    └─ vlm_describe(image_path) → SMILES               │
│    ├─ LLM section prompt → 结构化 JSON                     │
│    └─ try/catch: 失败 → uncertain_items，继续下一 section  │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌─ Stage 3: 合并 + 验证 + SAR ──────────────────────────────┐
│  ├─ section 结果去重 (E041 如果在两个 section 都出现)       │
│  ├─ 文字提取 ↔ VLM 图像结果交叉验证                         │
│  ├─ 构效关系分析                                           │
│  ├─ uncertain_items 整合                                   │
│  └─ LLM merge prompt → final StructuredData                │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌─ Stage 4: 输出 ──────────────────────────────────────────┐
│  ├─ 程序化生成 Markdown 报告 (generate_report)             │
│  ├─ 组装 DocumentReport                                   │
│  └─ emit to frontend via Tauri event                       │
└──────────────────────────────────────────────────────────┘
```

---

## 3. 与聊天 Agent 的分工

| 维度 | Chat Agent (`core/agent.rs`) | Doc Agent (pipeline 增强) |
|------|-----|------|
| 触发方式 | 用户发消息 | 用户拖入/选择文件 |
| 状态 | 有状态（多轮对话） | 无状态（单次任务） |
| 返回 | text stream | structured JSON |
| 工具 | KB/分子检索、文件读写 | PDF parse、VLM、分类器 |
| Prompt | 通用助手 prompt | 文档分析专用 prompt |
| 记忆 | 持久化到磁盘 | 不需要记忆 |

---

## 4. Prompt 体系

### Layer 1: Meta Prompt（文件级分析）

```
System: 你是文档分析专家。一次性读完整个文档内容，回答：
1. 这是什么类型的文档？（专利/论文/报告）
2. 文档结构是怎样的？
3. 有哪些需要进一步分析的图像？

只输出 200 字以内的简短描述。不要提取数据，只做结构分析。
```

目的：让 LLM 先对全局有认知，而非立刻开始提取细节。只读前 8000 字符。

### Layer 2: Section Prompt（分块分析）

```
你的任务是从以下文档段落中提取科学数据。

文档类型: {doc_type}
所属部分: {section_name}

要求：
1. 识别所有提到的化合物（名称+SMILES+结构特征）
2. 提取所有活性数据（pIC50/IC50/EC50 + 值 + 单位 + 靶点）
3. 标注置信度（high/medium/low），low 必须说原因
4. 不确定的放入 uncertain_items

输出 JSON 格式（不要其他文字）：
{compounds: [...], activities: [...], findings: [...], uncertain_items: [...]}
```

### Layer 3: Image Prompt（化学结构识别）

```
System: 你是化学结构识别专家。将图片中的化学结构转换为 SMILES。
只输出 SMILES 字符串，不要其他说明。

如果图片包含多个化合物，输出数组格式：
["SMILES1", "SMILES2", ...]
```

调用方式：Agent 检测到 ImageRef 中有未处理的化学结构图 → 调 VLM（vlm/describe）→ 结果存入 ImageRef.smiles。

### Layer 4: Merge Prompt（合并验证）

```
请验证并合并以下多部分提取结果，生成最终报告。

原始文档类型: {doc_type}
各部分的提取结果：{results_from_all_sections}
图片 VLM 识别的 SMILES：{smiles_from_images}

验证要求：
1. 检查数据一致性（如 E041 在两个部分都出现但 pIC50 不同）
2. 将结构式与活性数据关联
3. 进行 SAR 分析
4. 标注不确定项

最终输出 JSON（唯一输出，不要其他文字）：
{
  metadata: {title, doc_type, key_targets, authors},
  compounds: [{name, smiles, description, source_ref, confidence, uncertainty_reason}],
  activities: [{compound, activity_type, value, units, target, source_quote, source_ref, confidence}],
  key_findings: [{finding, evidence, source_ref, confidence}],
  sar_analysis: "构效关系总结（500字以内）",
  uncertain_items: [{item_type, content, reason, suggested_action}]
}
```

---

## 5. 数据结构

### DocProcessingContext

```rust
/// 整个 process 期间传递的状态
pub struct DocProcessingContext {
    // 文件来源
    pub source_path: PathBuf,
    pub parser_used: String,           // "pdf_inspector" | "mineru"

    // 原始内容
    pub raw_text: String,
    pub images: Vec<ImageRef>,
    pub page_count: usize,

    // 分析中间结果
    pub doc_type: Option<String>,       // "patent" | "paper" | "report"
    pub metadata: Option<DocumentMeta>,

    // 用户要求
    pub user_request: String,
}

pub struct ImageRef {
    pub filename: String,               // "images/page_05_img_02.png"
    pub page: usize,
    pub region: Option<String>,         // "figure" | "table" | "structure" | "unknown"
    pub description: Option<String>,    // VLM 描述结果
    pub smiles: Option<String>,         // 如果是化学结构
}
```

### ExtractionPlan（意图路由输出）

```rust
pub struct ExtractionPlan {
    pub target_sections: Vec<SectionRef>,
    pub extraction_types: Vec<String>,      // "compounds" | "activities" | "both"
    pub skip_sections: Vec<String>,
}
```

### DocumentReport（最终输出）

```rust
pub struct DocumentReport {
    pub metadata: DocumentMeta,
    pub compounds: Vec<CompoundEntry>,
    pub activities: Vec<ActivityRecord>,
    pub key_findings: Vec<Finding>,
    pub sar_analysis: String,
    pub uncertain_items: Vec<UncertainItem>,
    pub report_markdown: String,
}
```

---

## 6. A/B 并行计划

### 设计原则

- A 做 Pipeline 本身（intent + VLM + report）
- B 做数据层（relations + dedup + cluster + SAR）
- 共享 `types.rs` 的数据结构，互不冲突

### A 计划：Pipeline 增量改造

| 阶段 | 文件 | 内容 |
|------|------|------|
| A1 | `parsers/intent.rs` | 意图路由：`interpret_request` + `DocStructure` 解析 |
| A2 | `parsers/vlm_chem.rs` | VLM 化学识别：调 Python sidecar → SMILES |
| A3 | `parsers/pipeline.rs` | 主链整合：A1+A2 接入 pipeline，加 try/catch |
| A4 | `parsers/report.rs` | 报告生成：程序化 Markdown，不依赖 LLM |

### B 计划：分子关系层

| 阶段 | 文件 | 内容 |
|------|------|------|
| B1 | `core/molecule_db.rs` | `molecule_relations` 表 + CRUD |
| B2 | `core/molecule_dedup.rs` | 去重：Tanimoto 相似度 + same_as 关系 |
| B3 | `core/molecule_cluster.rs` | 聚类持久化：cluster 关系写入 |
| B4 | `core/sar_query.rs` | SAR 查询：analogs / cliffs / scaffold profile |

### 并行执行矩阵

| 阶段 | Agent A (Pipeline) | Agent B (数据层) |
|------|-------------------|-----------------|
| 第 1 轮 | A1: intent.rs + 测试 | B1: molecule_relations 表 + 测试 |
| 第 2 轮 | A2: vlm_chem.rs + 测试 | B2: molecule_dedup.rs + 测试 |
| 第 3 轮 | A3: pipeline 主链整合 | B3: 聚类持久化 + 测试 |
| 第 4 轮 | A4: report.rs + 测试 | B4: sar_query.rs + 测试 |
| 合并 | A+B: Tauri command 注册 + 前端 bridge |

### 任务边界

- **A 不碰**：`molecule_db`、`relations`、`dedup`、`cluster`、`sar_query`
- **B 不碰**：`pipeline.rs`、`post_process.rs`、`intent.rs`、`vlm_chem.rs`、`report.rs`
- **共享**：`types.rs` 中的数据结构定义（谁先到谁定义，另一个 import）

---

## 7. A/B 交互接口

```
A 产出: PdfParseResult { compounds, activities, ... }
         ↓ 写入
B 产出: MoleculeDatabase { molecules, relations, activities }
         ↑ 读取
A 产出: DocumentReport (可选，从 B 的数据生成)
```

---

## 8. 验收标准

### A 计划验收

```bash
cd src-tauri
cargo test -- --ignored  # 现有 pipeline 测试仍通过
cargo test                # 新 intent/vlm/report 测试通过

# 手动验证：
# invoke('parse_pdf', { path: 'test.pdf', user_request: '提取 TABLE 1' })
# → 只处理 TABLE 1，不跑全量
```

### B 计划验收

```bash
cd src-tauri
cargo test                # relations/dedup/cluster/sar 测试通过

# 手动验证：
# add_relation("mol_001", "mol_002", "similar", 0.87)
# get_similar_molecules("mol_001", 0.8) → [{"mol_002", 0.87}]
```

### 合并验收

```bash
# 端到端：parse_pdf → 提取分子 → 写入 relations → SAR 查询
# Tauri command 全部注册
# TypeScript bridge 全部导出
```

---

## 9. 分子关系层详细设计

### 9.1 molecule_relations 表

```sql
CREATE TABLE IF NOT EXISTS molecule_relations (
    id INTEGER PRIMARY KEY,
    mol_a_id TEXT NOT NULL,
    mol_b_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,    -- "similar" | "same_as" | "scaffold" | "cluster"
    score REAL,                     -- tanimoto 等
    metadata TEXT,                  -- JSON 扩展
    created_at TEXT NOT NULL,
    FOREIGN KEY (mol_a_id) REFERENCES molecules(id),
    FOREIGN KEY (mol_b_id) REFERENCES molecules(id),
    UNIQUE(mol_a_id, mol_b_id, relation_type)
);

CREATE INDEX idx_relations_type ON molecule_relations(relation_type);
CREATE INDEX idx_relations_a ON molecule_relations(mol_a_id);
CREATE INDEX idx_relations_b ON molecule_relations(mol_b_id);
```

### 9.2 四种关系类型

| 类型 | 用途 | score 含义 |
|------|------|-----------|
| `similar` | 分子相似度 | tanimoto 系数 (0-1) |
| `same_as` | 去重标记 | 置信度 (0-1) |
| `scaffold` | 骨架归属 | NULL |
| `cluster` | 聚类归属 | NULL（cluster_id 在 metadata 中） |

### 9.3 SAR 查询

```rust
/// 找到分子的所有近似类似物及其活性
pub fn find_analogs_with_activity(mol_id, min_similarity) -> Vec<AnalogWithActivity>

/// 找到 scaffold 上所有分子的活性谱
pub fn scaffold_activity_profile(scaffold) -> ScaffoldProfile

/// 识别 activity cliff（结构相似但活性差异大）
/// 定义：tanimoto > 0.8 且活性差 > 10 倍
pub fn find_activity_cliffs(min_similarity, min_activity_diff) -> Vec<ActivityCliff>
```
