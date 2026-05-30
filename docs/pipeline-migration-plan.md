# PDF Pipeline Python → Rust 迁移计划

> 日期：2026-05-30
> 目标：将 `PDFParserPipeline`（Python）的全部能力迁移到 Rust/Tauri，消除对 Python sidecar 的依赖

---

## 现状

两条独立管道并行运行：

| 管道 | 执行位置 | 用途 | 入口 |
|------|----------|------|------|
| `parse_pdf` / `process_document` | Rust/Tauri | 前端交互式 PDF 解析 | Tauri command |
| `PDFParserPipeline` | Python/model server | 项目批量索引 | `/api/v1/project/index` |

**迁移目标**：删除 Python 管道，统一到 Rust。

---

## 差距分析

### Rust 已有 ✅

- 文本提取（pdf_inspector / mineru / uniparser / llama_parse 4 后端）
- 文档级分类
- 文本分块
- 正则 SMILES 提取（无 RDKit 验证）
- 正则活性数据提取
- LLM 后处理（StructuredData + Markdown 报告）
- 意图路由（intent.rs）
- MolScribe 图片→SMILES（通过 Python sidecar）

### Rust 缺失 ❌

| 缺失能力 | 难度 | 依赖 |
|----------|------|------|
| 嵌入式图片提取（PyMuPDF 等价） | 中 | `lopdf` 或 `pdf-extract` |
| 通用 VLM 图片描述 | 中 | Python sidecar（已有） |
| L0/L1/L2 分层摘要 | 中 | LLM HTTP |
| 分子数据库（SQLite + FTS5） | 中 | `rusqlite` |
| SMILES-活性位置关联 | 低 | 纯逻辑 |
| AssociationEngine（上下文解析） | 低 | 纯正则 |
| 关键词/实体提取 | 低 | 纯逻辑 |
| 摘要持久化 | 低 | 文件 IO |
| 待确认提取工作流 | 低 | JSON 文件 |
| ROI 文本提取 | 中 | PDF 解析 |
| ChromaDB 向量索引 | 高 | 嵌入模型 HTTP + ChromaDB |
| 语义搜索 / RAG | 高 | 向量索引 |
| MolDetv2 YOLO 检测 | 高 | ONNX Runtime |
| RDKit 分子属性计算 | 高 | RDKit 或 sidecar |

---

## 迁移策略

**原则**：
1. 纯逻辑直接用 Rust 重写（最快）
2. 需要 LLM/VLM 的走 HTTP 调用（保持 sidecar）
3. 重型 ML 推理（YOLO、ChromaDB）走 sidecar 或逐步迁移
4. 每个阶段独立可测试，不破坏现有功能

---

## Phase 1：纯逻辑迁移（无外部依赖）

**目标**：把不依赖任何外部服务的纯逻辑模块搬到 Rust

### 1.1 SMILES-活性位置关联

**来源**：`parsers/molecule/molecule_extractor.py` 的 `extract_from_text`
**Rust 目标**：`src-tauri/src/commands/extractor.rs` 扩展

```rust
pub struct AssociatedMolecule {
    pub smiles: String,
    pub activity: Option<ActivityData>,
    pub position: usize,
    pub confidence: String,
}

/// 从文本中提取 SMILES + 活性数据，并按位置关联
pub fn extract_associated_molecules(text: &str, doc_id: &str) -> Vec<AssociatedMolecule>
```

逻辑：两个正则分别提取 SMILES 和活性，然后按文本位置 proximity matching（200 字符窗口内关联）。

### 1.2 AssociationEngine（上下文解析）

**来源**：`parsers/molecule/association_engine.py`
**Rust 目标**：`src-tauri/src/parsers/association.rs`（新文件）

从分子图片周围的文本中解析：
- 化合物名称（Compound 1, Fig. 1, Scheme 1）
- 活性数据
- 细胞系/靶点

纯正则 + 规则，无外部依赖。

### 1.3 关键词/实体提取

**来源**：`core/summarizer.py` 的关键词提取
**Rust 目标**：`src-tauri/src/parsers/keywords.rs`（新文件）

基于词频的关键词提取 + 实体标签（化合物名、靶点名、方法名）。

### 1.4 分层摘要持久化

**来源**：`core/summary_manager.py`
**Rust 目标**：`src-tauri/src/core/summary.rs`（新文件）

```rust
pub struct DocumentSummary {
    pub doc_id: String,
    pub l0_abstract: String,      // ~100 tokens
    pub l1_overview: String,      // ~2000 tokens
    pub l2_detail: String,        // pointer to full content
    pub keywords: Vec<String>,
    pub entities: Vec<String>,
}

pub struct SummaryManager;
impl SummaryManager {
    pub fn save(&self, project_root: &Path, doc_id: &str, summary: &DocumentSummary) -> Result<()>;
    pub fn load(&self, project_root: &Path, doc_id: &str) -> Result<DocumentSummary>;
}
```

写入 `.mbforge/summaries/{doc_id}.json`。

### 1.5 待确认提取工作流

**来源**：`parsers/molecule/mol_image_pipeline.py` 的 pending.json
**Rust 目标**：`src-tauri/src/core/pending.rs`（新文件）

```rust
pub fn save_pending(project_root: &Path, doc_id: &str, extractions: &[ExtractionResult]) -> Result<()>;
pub fn load_pending(project_root: &Path, doc_id: &str) -> Result<Vec<ExtractionResult>>;
```

**验收**：`cargo test` 覆盖上述所有模块的单元测试。

---

## Phase 2：SQLite 分子数据库

**目标**：Rust 实现 MoleculeDatabase，替代 Python 的 `core/mol_database.py`

### 2.1 表结构

```sql
CREATE TABLE molecules (
    mol_id TEXT PRIMARY KEY,
    smiles TEXT NOT NULL,
    name TEXT,
    source_doc TEXT,
    activity REAL,
    activity_type TEXT,
    units TEXT,
    source_type TEXT,          -- "text" | "image" | "manual"
    status TEXT DEFAULT 'pending',
    properties TEXT,           -- JSON: {mw, logp, hbd, hba, tpsa, rotatable_bonds}
    tags TEXT,                 -- JSON array
    notes TEXT,
    created_at TEXT
);

CREATE INDEX idx_mol_smiles ON molecules(smiles);
CREATE INDEX idx_mol_source ON molecules(source_doc);
CREATE INDEX idx_mol_status ON molecules(status);

CREATE VIRTUAL TABLE molecules_fts USING fts5(
    name, notes, smiles, content=molecules, content_rowid=rowid
);
```

### 2.2 核心 API

```rust
pub struct MoleculeDatabase { db_path: PathBuf, conn: Connection }

impl MoleculeDatabase {
    pub fn open(project_root: &Path) -> Result<Self>;
    pub fn add_molecule(&self, mol: &MoleculeRecord) -> Result<String>;
    pub fn get_molecule(&self, mol_id: &str) -> Option<MoleculeRecord>;
    pub fn search_smiles(&self, smiles: &str) -> Vec<MoleculeRecord>;
    pub fn search_text(&self, query: &str) -> Vec<MoleculeRecord>;  // FTS5
    pub fn list_by_doc(&self, doc_id: &str) -> Vec<MoleculeRecord>;
    pub fn stats(&self) -> MoleculeStats;
    pub fn update_status(&self, mol_id: &str, status: &str) -> Result<()>;
}
```

### 2.3 分子属性计算

**方案选择**：
- **选项 A**：用 `rdkit` crate（Rust binding）→ 需要编译 RDKit，重量级
- **选项 B**：调 Python sidecar `/api/v1/molecule/properties` → 保持 sidecar 依赖
- **选项 C**：简单属性用正则/规则计算，复杂属性走 sidecar → 折中

**推荐**：选项 C。MW 从 SMILES 估算（原子质量求和），LogP/TPSA 用简化的碎片法。复杂属性按需调 sidecar。

**验收**：单元测试覆盖 CRUD、FTS 搜索、属性计算。

---

## Phase 3：PDF 图片提取 + 通用 VLM

**目标**：从 PDF 提取嵌入图片，调 VLM 做通用图片描述

### 3.1 嵌入式图片提取

**来源**：`pdf_parser.py` 的 `_extract_limited_images`
**Rust 方案**：用 `lopdf` crate（纯 Rust PDF 解析）

```rust
pub struct ExtractedImage {
    pub page: usize,
    pub filename: String,     // page_{N}_img_{M}.{ext}
    pub path: PathBuf,
    pub width: u32,
    pub height: u32,
}

pub fn extract_images_from_pdf(pdf_path: &str, output_dir: &Path, max_images: usize, max_size_mb: usize) -> Vec<ExtractedImage>
```

### 3.2 通用 VLM 图片描述

**Rust 方案**：HTTP 调 Python sidecar `/api/v1/vlm/describe`

```rust
pub async fn describe_image(image_path: &str, context: &str, vlm_url: &str) -> Result<String, String>
```

**验收**：用测试 PDF 验证图片提取 + VLM 描述。

---

## Phase 4：LLM 分层摘要

**目标**：实现 L0/L1/L2 分层摘要系统

### 4.1 L0 摘要（一句话）

```rust
pub async fn generate_l0_abstract(content: &str, llm_url: &str) -> Result<String, String>
// prompt: "用一句话概括这篇文档的核心内容，不超过 100 字。"
```

### 4.2 L1 概览（结构化）

```rust
pub async fn generate_l1_overview(content: &str, llm_url: &str) -> Result<L1Overview, String>
// prompt: 要求输出 JSON: {background, methods, key_results, molecules, activity_data}
```

### 4.3 组合管道

```rust
pub async fn generate_summaries(content: &str, llm_url: &str) -> Result<DocumentSummary, String> {
    let l0 = generate_l0_abstract(content, llm_url).await?;
    let l1 = generate_l1_overview(content, llm_url).await?;
    let keywords = extract_keywords(content);
    Ok(DocumentSummary { l0_abstract: l0, l1_overview: l1.to_json(), keywords, .. })
}
```

**验收**：用测试文档验证 L0/L1 质量。

---

## Phase 5：ROI 文本提取 + 待确认流程

**目标**：从分子检测框周围提取上下文文本

### 5.1 ROI 文本提取

**来源**：`parsers/molecule/roi_text_extractor.py`
**Rust 方案**：基于 PDF 页面坐标 + 文本块定位

```rust
pub struct RoiTextResult {
    pub above: String,    // 框上方文本（标题/说明）
    pub below: String,    // 框下方文本（图注）
    pub inside: String,   // 框内文本（标签）
}

pub fn extract_roi_text(pdf_path: &str, page: usize, bbox: (f64, f64, f64, f64)) -> RoiTextResult
```

### 5.2 完整图片分子提取管道

整合 Phase 1 的 AssociationEngine + Phase 5 的 ROI + Phase 3 的 MolScribe：

```rust
pub async fn extract_molecules_from_images(
    pdf_path: &str,
    images: &[ExtractedImage],
    vlm_url: &str,
) -> Vec<ExtractionResult>
```

**验收**：端到端测试：PDF → 图片提取 → MolScribe → ROI → 关联。

---

## Phase 6：ChromaDB 向量索引

**目标**：实现文档向量化 + 语义搜索

### 6.1 嵌入生成

调 Python sidecar `/api/v1/embed`：

```rust
pub async fn embed_texts(texts: &[String], embed_url: &str) -> Result<Vec<Vec<f32>>, String>
```

### 6.2 ChromaDB 操作

**方案选择**：
- **选项 A**：Rust 直接操作 ChromaDB HTTP API → ChromaDB 有 REST API
- **选项 B**：用 `chromadb` Rust client（如果存在）
- **选项 C**：自建向量索引（`hnswlib-rust` 或 `usearch`）

**推荐**：选项 A，ChromaDB HTTP API。ChromaDB 本身就是服务，Rust 通过 HTTP 操作最简单。

```rust
pub struct KnowledgeBase {
    chroma_url: String,
    embed_url: String,
    collection: String,
}

impl KnowledgeBase {
    pub fn new(chroma_url: &str, embed_url: &str) -> Self;
    pub async fn index_document(&self, doc_id: &str, chunks: &[String], metadata: &serde_json::Value) -> Result<()>;
    pub async fn search(&self, query: &str, top_k: usize) -> Vec<SearchResult>;
    pub async fn hybrid_search(&self, query: &str, top_k: usize) -> Vec<SearchResult>;
}
```

### 6.3 搜索 API

```rust
pub struct SearchResult {
    pub chunk: String,
    pub score: f64,
    pub doc_id: String,
    pub metadata: serde_json::Value,
}
```

**验收**：索引测试文档 → 语义搜索 → 返回相关结果。

---

## Phase 7：Rust Tauri 命令注册 + 前端集成

**目标**：把 Phase 1-6 的能力注册为 Tauri 命令，前端调用

### 7.1 新增 Tauri 命令

```rust
// 批量索引（替代 Python /index 端点）
#[tauri::command]
async fn index_project(app: AppHandle, root: String) -> Result<IndexResult, String>

// 增量索引（流式进度）
#[tauri::command]
async fn index_project_stream(app: AppHandle, root: String) -> Result<(), String>

// 语义搜索
#[tauri::command]
async fn kb_search(project_root: String, query: String, top_k: usize) -> Vec<SearchResult>

// 分子数据库查询
#[tauri::command]
fn mol_list(project_root: String, limit: usize, offset: usize) -> Vec<MoleculeRecord>
```

### 7.2 前端 bridge 更新

`frontend/src/api/tauri-bridge.ts` 新增对应函数。

**验收**：前端可以触发批量索引、搜索、分子查询。

---

## Phase 8：清理 Python 管道

**目标**：删除不再需要的 Python 代码

### 可删除

| 文件 | 原因 |
|------|------|
| `src/mbforge/parsers/pdf_parser.py` | 被 Rust pipeline 替代 |
| `src/mbforge/model_server/routers/project.py` 的 `/index` 端点 | 被 Tauri 命令替代 |
| `src/mbforge/core/knowledge_base.py` | 被 Rust KnowledgeBase 替代 |
| `src/mbforge/core/summary_manager.py` | 被 Rust SummaryManager 替代 |
| `src/mbforge/core/mol_database.py` | 被 Rust MoleculeDatabase 替代 |
| `src/mbforge/parsers/molecule/molecule_extractor.py` | 被 Rust extractor 替代 |
| `src/mbforge/parsers/molecule/association_engine.py` | 被 Rust association 替代 |
| `src/mbforge/parsers/molecule/roi_text_extractor.py` | 被 Rust ROI 替代 |

### 保留（仍被其他功能使用）

| 文件 | 原因 |
|------|------|
| `src/mbforge/model_server/routers/vlm.py` | VLM sidecar 端点 |
| `src/mbforge/model_server/routers/embed.py` | 嵌入 sidecar 端点 |
| `src/mbforge/model_server/routers/moldet.py` | MolDet sidecar 端点 |
| `src/mbforge/parsers/molecule/mol_image_pipeline.py` | MolDetv2 + MolScribe（如果 YOLO 不迁移） |
| `src/mbforge/models/` | 模型抽象层（被 sidecar 端点使用） |

**验收**：`mbforge index` CLI 命令改为调 Tauri 命令，Python 管道代码全部删除。

---

## 执行顺序

```
Phase 1 (纯逻辑)    ← 可立即开始，无外部依赖
    ↓
Phase 2 (SQLite)    ← 需要 rusqlite，无外部服务
    ↓
Phase 3 (图片+VLM)  ← 需要 lopdf + VLM sidecar
    ↓
Phase 4 (摘要)      ← 需要 LLM sidecar
    ↓
Phase 5 (ROI+完整管道) ← 整合 Phase 1-4
    ↓
Phase 6 (向量索引)  ← 需要 ChromaDB + 嵌入 sidecar
    ↓
Phase 7 (Tauri 注册) ← 整合全部
    ↓
Phase 8 (清理)      ← 删除 Python 管道
```

**每个 Phase 独立可交付**，不依赖后续 Phase。Phase 1-2 可以立即并行开发。
