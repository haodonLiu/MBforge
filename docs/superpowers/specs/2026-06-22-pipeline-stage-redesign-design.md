# PDF Pipeline Stage 重构设计

> 状态：设计中  
> 日期：2026-06-22  
> 范围：`src-tauri/src/parsers/pipeline/` 端到端重构  
> 目标：工程可维护性优先，允许全新接口

---

## 1. 背景与问题

当前 PDF 解析管线代码存在以下可维护性问题：

1. **文件过大、职责混杂**
   - `extract.rs` 超过 1800 行，同时包含：图片持久化、OCR 缓存、分类提取、分子提取、快速 MoldDet 扫描等。
   - `pipeline.rs` 超过 2200 行，`process_document` 一个函数串联了提取、分节、LLM 提取、分子识别、图片描述、合并、验证、持久化、索引等全部步骤。

2. **数据流向不清晰**
   - `DocProcessingContext` 塞入了几乎所有中间状态，Stage 之间通过可变字段共享数据，难以追踪哪个步骤修改了哪个字段。
   - `ClassifyResult`、`OcrOutput`、`SectionChunk`、`StructuredData` 等类型之间的转换路径散落在多个文件中。

3. **错误处理薄弱**
   - 大量 `Result<T, String>` 传播，错误来源和上下文不清晰，UI 只能展示裸字符串。

4. **进度/可观测性耦合**
   - Stage 内部直接调用 `app.emit(...)`，与 Tauri 强耦合，测试困难。

5. **缓存抽象缺失**
   - 文件缓存、OCR 缓存、检测缓存三种实现各自为政，没有统一接口。

---

## 2. 设计目标

1. **职责单一**：每个文件/模块只负责一个明确概念。
2. **类型驱动**：Stage 之间通过不可变数据模型传递，禁止可变共享状态。
3. **错误可追踪**：引入结构化错误类型，替代裸字符串。
4. **进度可观测**：通过抽象 reporter 发射事件，Stage 不直接依赖 Tauri。
5. **可测试**：每个 Stage 和服务可独立测试、可 mock。
6. **缓存统一**：抽象通用 Cache 接口。

---

## 3. 整体架构

将 `src-tauri/src/parsers/pipeline/` 重构成 **Stage Pipeline**：

```text
pipeline/
├── mod.rs              # 对外导出
├── runner.rs           # PipelineRunner + Stage trait
├── error.rs            # PipelineError + StageError
├── context.rs          # PipelineContext + PipelineReporter trait
├── stages/
│   ├── mod.rs
│   ├── extract.rs      # Stage 1: PDF → ExtractedDocument
│   ├── segment.rs      # Stage 2: ExtractedDocument → SegmentedDocument
│   ├── enrich.rs       # Stage 3: SegmentedDocument → EnrichedDocument
│   ├── persist.rs      # Stage 4: EnrichedDocument → PersistedDocument
│   └── index.rs        # Stage 5: PersistedDocument → IndexedDocument
├── models/
│   ├── mod.rs
│   ├── source.rs       # SourceInput
│   ├── extracted.rs    # ExtractedDocument, ImageRef, OcrBlock
│   ├── segmented.rs    # SegmentedDocument, SectionChunk, TreeNode
│   ├── enriched.rs     # EnrichedDocument, StructuredData
│   └── persisted.rs    # PersistedDocument, IndexedDocument
├── services/
│   ├── mod.rs
│   ├── source.rs       # SourceResolver
│   ├── inspector.rs    # PdfInspectorService
│   ├── ocr.rs          # OcrService（backend 调度 + 缓存）
│   ├── images.rs       # ImageService（提取 + 持久化）
│   ├── cache.rs        # Cache trait + FileCache/OcrCache/DetectionCache
│   ├── section_processor.rs  # 并行 section LLM 提取
│   ├── molecules.rs    # MolDet + MolScribe + 缓存
│   ├── captions.rs     # VLM 图片描述
│   ├── merge.rs        # StructuredData 合并 + SAR
│   └── chem_validate.rs # RDKit 校验封装
└── writer/
    ├── mod.rs
    ├── text_md.rs      # text.md 生成
    └── report_md.rs    # report.md 生成
```

---

## 4. 核心接口

### 4.1 Stage Trait

每个 Stage 实现统一接口：

```rust
#[async_trait]
pub trait Stage<Input, Output> {
    async fn run(&self, input: Input, ctx: &PipelineContext) -> Result<StageOutcome<Output>, PipelineError>;
}
```

`StageOutcome` 包含输出、日志和警告：

```rust
pub struct StageOutcome<T> {
    pub output: T,
    pub logs: Vec<StageLog>,
    pub warnings: Vec<String>,
}
```

### 4.2 PipelineContext

Stage 之间共享的只读上下文：

```rust
pub struct PipelineContext {
    pub source_path: PathBuf,
    pub project_root: Option<PathBuf>,
    pub user_request: String,
    pub reporter: Arc<dyn PipelineReporter>,
    pub config: PipelineConfig,
}
```

`PipelineReporter` 抽象进度报告：

```rust
pub trait PipelineReporter: Send + Sync {
    fn report(&self, event: PipelineEvent);
}
```

Tauri 实现将事件转换为 `EVT_DOC_PROGRESS`；测试实现可收集事件到 Vec。

### 4.3 PipelineError

按 Stage 分类的结构化错误：

```rust
pub enum PipelineError {
    Extract(ExtractError),
    Segment(SegmentError),
    Enrich(EnrichError),
    Persist(PersistError),
    Index(IndexError),
}

pub enum ExtractError {
    InspectorFailed { path: String, source: String },
    OcrFailed { backend: String, source: String },
    ImagePersistFailed { filename: String, source: String },
}
```

---

## 5. 数据流

```text
SourceInput
    │
    ▼
┌─────────────┐
│   Extract   │  ← 读取文件缓存 → 未命中则 pdf-inspector → 如需 OCR 调 backend → 图片持久化
└─────────────┘
    │
    ▼ ExtractedDocument
┌─────────────┐
│   Segment   │  ← extract_headings → build_sections → build_tree
└─────────────┘
    │
    ▼ SegmentedDocument
┌─────────────┐
│   Enrich    │  ← 并行 section LLM 提取 + 分子识别 + 图片描述 + 合并/SAR + RDKit 校验
└─────────────┘
    │
    ▼ EnrichedDocument
┌─────────────┐
│   Persist   │  ← 写 text.md / report.md / 分子库
└─────────────┘
    │
    ▼ PersistedDocument
┌─────────────┐
│   Index     │  ← section embedding → KB 索引 → 文件缓存
└─────────────┘
    │
    ▼ IndexedDocument
```

所有 Stage 输出均为不可变数据。如果下游需要上游原始信息（例如 Persist 需要 `raw_text` 和 `images`），则把 `ExtractedDocument` 作为附加参数传入，而不是在 Enrich 里塞入所有字段。

---

## 6. Stage 详细设计

### 6.1 Extract Stage

**输入**：`SourceInput { path, project_root, allow_ocr }`

**输出**：`ExtractedDocument`

```rust
pub struct ExtractedDocument {
    pub raw_text: String,
    pub page_count: usize,
    pub parser: String,
    pub images: Vec<ImageRef>,
    pub ocr_blocks: Vec<OcrBlock>,
    pub metadata: ExtractedMetadata,  // 例如 title, authors, document_type 等从文本或 filename 推断的元数据
}
```

**内部服务**：

| 服务 | 职责 |
|------|------|
| `SourceResolver` | 定位 project_root、doc_id、source path |
| `InspectorService` | pdf-inspector 原始文本提取 |
| `OcrService` | OCR backend 轮询与结果缓存 |
| `ImageService` | PDF 内嵌图片提取 + backend 图片持久化到 `reports/figures/` |
| `FileCacheService` | 文件缓存读写 |

**流程**：
1. `SourceResolver` 解析路径。
2. 查 `FileCache`：命中则直接返回缓存的 `ExtractedDocument`。
3. 未命中则 `InspectorService` 提取原始 markdown。
4. 判断是否为扫描件；若是且允许 OCR，先查 `OcrCache`，未命中则调 `OcrService` 轮询 backend。
5. `ImageService` 提取并持久化图片。
6. 合并文本，写入 `FileCache` 和 `OcrCache`。

### 6.2 Segment Stage

**输入**：`ExtractedDocument`

**输出**：`SegmentedDocument`

```rust
pub struct SegmentedDocument {
    pub sections: Vec<SectionChunk>,
    pub document_tree: Vec<TreeNode>,
    pub headings: Vec<Heading>,
}
```

**内部步骤**：
1. `extract_headings(&raw_text)` 提取 Markdown 标题。
2. 若有标题，按标题切分 section；若无标题，走语义分块。
3. 超长 section 二次拆分：先语义边界，后 `text-splitter`。
4. `build_tree(&sections)` 生成结构树。

### 6.3 Enrich Stage

**输入**：`SegmentedDocument` + `ExtractedDocument`（需要 images）

**输出**：`EnrichedDocument`

```rust
pub struct EnrichedDocument {
    pub structured_data: StructuredData,
    pub sar_analysis: Option<String>,
    pub molecule_results: Vec<DetectedMolecule>,
    pub image_captions: HashMap<String, String>,
    pub sections: Vec<SectionChunk>,
}
```

**内部服务**：

| 服务 | 职责 |
|------|------|
| `SectionProcessor` | 并行 LLM 提取每个 section |
| `MoleculeService` | MolDet 检测 + MolScribe 识别 + detection cache |
| `ImageCaptionService` | 非结构图的 VLM 描述 + caption cache |
| `StructuredDataMerger` | 合并 section 结果 + 跑 SAR 分析 |
| `ChemValidator` | RDKit 结构校验与规范化 |

### 6.4 Persist Stage

**输入**：`EnrichedDocument` + `ExtractedDocument`

**输出**：`PersistedDocument`

```rust
pub struct PersistedDocument {
    pub doc_id: String,
    pub text_md_path: PathBuf,
    pub report_md_path: PathBuf,
    pub unverified_image_count: usize,
    pub persisted_molecule_count: usize,
}
```

**内部 Writer**：
- `TextMdWriter`：生成 `text.md`（头部 + augment_markdown_with_images + 图片校对表）。
- `ReportMdWriter`：生成 `report.md`。
- `MoleculeStoreWriter`：写入 SQLite 分子库。

### 6.5 Index Stage

**输入**：`PersistedDocument`

**输出**：`IndexedDocument`

```rust
pub struct IndexedDocument {
    pub doc_id: String,
    pub indexed_sections: usize,
}
```

**内部服务**：
- `SectionEmbedder`：调用 sidecar 做 embedding。
- `VectorStoreWriter`：写入 KB 向量索引。
- `FileCacheWriter`：把 sections 写入文件缓存。

---

## 7. 缓存统一抽象

抽象通用接口：

```rust
pub trait Cache<K, V> {
    fn get(&self, key: &K) -> Result<Option<V>, CacheError>;
    fn put(&self, key: &K, value: &V) -> Result<(), CacheError>;
}
```

三种实现：

| 实现 | 键 | 值 | 用途 |
|------|-----|-----|------|
| `FileCache` | 文件路径 / doc_id | `{ text, sections_json, metadata_json }` | 避免重复解析整个 PDF |
| `OcrCache` | 文件 SHA-256 + 页列表 | `OcrOutput` | 避免重复调 OCR backend |
| `DetectionCache` | doc_id + page + pdf_hash | `PageDetection` | 避免重复 MoldDet |

Extract Stage 的缓存查询顺序：
1. 查 `FileCache`：命中则跳过整个 Extract。
2. 未命中则继续提取。
3. OCR 前先查 `OcrCache`。
4. 结果写入 `FileCache` 和 `OcrCache`。

---

## 8. 错误处理与可观测性

### 8.1 错误策略

- **致命错误**：Stage 失败，整条 pipeline 停止。例如文件读取失败、所有 OCR backend 失败。
- **可恢复错误**：转换为 warning，继续执行。例如某张图片 caption 失败、某个 section LLM 提取失败。
- **错误展示**：Tauri command 返回 `Result<(), PipelineError>`，前端按错误类型展示不同文案。

### 8.2 进度事件

`PipelineReporter` 统一处理进度：

```rust
pub enum PipelineEvent {
    StageStart { stage: String },
    StageProgress { stage: String, message: String },
    StageComplete { stage: String },
    StageWarning { stage: String, message: String },
}
```

Stage 内部调用 `ctx.reporter.report(PipelineEvent::StageProgress { ... })`，由 runner 或 Tauri adapter 决定如何转发到前端。

---

## 9. 测试策略

### 9.1 单元测试

每个 Stage 和 service 都有独立单元测试：

- `SegmentStage`：输入 fixture `ExtractedDocument`，验证 `sections` 和 `document_tree`。
- `OcrService`：注入 `MockOcrBackend`，验证轮询和降级逻辑。
- `ImageService`：使用临时目录验证图片复制和 `rel_path` 生成。

### 9.2 集成测试

- 端到端测试：用 2-3 个真实 PDF（文本型、扫描型、专利），跑完整 pipeline，验证产出 `text.md`、`report.md`、KB 索引。

### 9.3 Mock 策略

Service 层定义 trait：

```rust
#[async_trait]
pub trait OcrBackend: Send + Sync {
    fn name(&self) -> &'static str;
    fn is_available(&self) -> bool;
    async fn run(&self, path: &str) -> Result<OcrOutput, OcrError>;
}
```

测试时注入 `MockOcrBackend`、`MockInspectorService` 等。

---

## 10. 迁移策略

由于允许全新接口，建议一次性迁移：

1. 临时新建 `pipeline_v2/` 目录实现新架构，避免破坏现有构建。
2. 保留旧 `pipeline/` 目录直到新架构跑通所有测试并被调用方切换。
3. 更新 `commands/pdf.rs` 和 `core/document/ingest_worker.rs` 调用新 pipeline。
4. 前端调整：新 pipeline 返回 `PipelineError` 结构化错误，事件格式保持不变。
5. 新 pipeline 稳定后，删除旧 `pipeline/` 并把 `pipeline_v2/` 重命名为 `pipeline/`。
6. 旧代码删除前，确保新 pipeline 通过：单元测试 + 集成测试 + 手动端到端验证。

---

## 11. 风险与回退

| 风险 | 缓解措施 |
|------|---------|
| 一次性迁移工作量大 | 按 Stage 逐个实现，每实现一个就跑通对应测试 |
| 新接口影响前端 | 保持 Tauri event 名称和字段不变；command 返回类型升级但兼容 JSON 序列化 |
| 缓存格式变更 | 新 cache 使用新的 schema version，旧缓存自然 miss，不会 crash |
| 性能回退 | 对比新旧 pipeline 在处理 10/50/100 页 PDF 时的耗时 |

---

## 12. 成功标准

1. `pipeline/` 下没有超过 500 行的文件（测试除外）。
2. `process_document` 函数长度不超过 100 行。
3. 所有 Stage 都有独立单元测试覆盖。
4. pipeline Stage 接口和 service 接口不再使用 `Result<T, String>` 传播错误（底层第三方调用除外）。
5. `cargo test --lib parsers::pipeline` 全通过。
6. 端到端处理一个真实 PDF 后，`text.md` 和 `report.md` 正常生成。
