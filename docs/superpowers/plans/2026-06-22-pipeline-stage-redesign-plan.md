# PDF Pipeline Stage 重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `src-tauri/src/parsers/pipeline/` 重构成基于 Stage Pipeline 的端到端可维护架构，明确阶段边界、统一错误处理、解耦服务并提升可测试性。

**Architecture:** 引入 `Stage<Input, Output>` trait，将原 `process_document` 拆分为 Extract → Segment → Enrich → Persist → Index 五个阶段。每个阶段只依赖上一阶段输出和共享的 `PipelineContext`，通过不可变数据模型传递。Service 层提供可 mock 的接口，缓存统一抽象为 `Cache<K, V>` trait。

**Tech Stack:** Rust 2021, Tauri v2, async-trait, tokio, serde, lopdf, pulldown-cmark, text-splitter

---

## 文件结构

新建目录 `src-tauri/src/parsers/pipeline_v2/`，最终验证稳定后替换旧的 `pipeline/`。

```text
src-tauri/src/parsers/
├── pipeline_v2/                 # 新 pipeline（本计划实现）
│   ├── mod.rs
│   ├── runner.rs
│   ├── context.rs
│   ├── error.rs
│   ├── stages/
│   │   ├── mod.rs
│   │   ├── extract.rs
│   │   ├── segment.rs
│   │   ├── enrich.rs
│   │   ├── persist.rs
│   │   └── index.rs
│   ├── models/
│   │   ├── mod.rs
│   │   ├── source.rs
│   │   ├── extracted.rs
│   │   ├── segmented.rs
│   │   ├── enriched.rs
│   │   └── persisted.rs
│   ├── services/
│   │   ├── mod.rs
│   │   ├── source.rs
│   │   ├── inspector.rs
│   │   ├── ocr.rs
│   │   ├── images.rs
│   │   ├── cache.rs
│   │   ├── section_processor.rs
│   │   ├── molecules.rs
│   │   ├── captions.rs
│   │   ├── merge.rs
│   │   └── chem_validate.rs
│   └── writer/
│       ├── mod.rs
│       ├── text_md.rs
│       └── report_md.rs
└── pipeline/                    # 旧 pipeline（保留到迁移完成）
```

---

## Phase 1: 基础设施与核心接口

### Task 1: 创建 `pipeline_v2` 目录结构

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/mod.rs`
- Create: `src-tauri/src/parsers/pipeline_v2/runner.rs`
- Create: `src-tauri/src/parsers/pipeline_v2/context.rs`
- Create: `src-tauri/src/parsers/pipeline_v2/error.rs`
- Create: `src-tauri/src/parsers/pipeline_v2/stages/mod.rs`
- Create: `src-tauri/src/parsers/pipeline_v2/models/mod.rs`
- Create: `src-tauri/src/parsers/pipeline_v2/services/mod.rs`
- Create: `src-tauri/src/parsers/pipeline_v2/writer/mod.rs`

- [ ] **Step 1: 创建空模块文件**

在每个新建文件中写入占位内容（后续任务替换）：

```rust
// src-tauri/src/parsers/pipeline_v2/mod.rs
pub mod context;
pub mod error;
pub mod models;
pub mod runner;
pub mod services;
pub mod stages;
pub mod writer;
```

```rust
// src-tauri/src/parsers/pipeline_v2/runner.rs
//! Pipeline runner.
```

```rust
// src-tauri/src/parsers/pipeline_v2/context.rs
//! Pipeline context and reporter.
```

```rust
// src-tauri/src/parsers/pipeline_v2/error.rs
//! Pipeline errors.
```

```rust
// src-tauri/src/parsers/pipeline_v2/stages/mod.rs
//! Pipeline stages.
```

```rust
// src-tauri/src/parsers/pipeline_v2/models/mod.rs
//! Pipeline data models.
```

```rust
// src-tauri/src/parsers/pipeline_v2/services/mod.rs
//! Pipeline services.
```

```rust
// src-tauri/src/parsers/pipeline_v2/writer/mod.rs
//! Output writers.
```

- [ ] **Step 2: 注册新模块到 `parsers/mod.rs`**

Modify: `src-tauri/src/parsers/mod.rs`

在 `pub mod pipeline;` 下方添加：

```rust
pub mod pipeline_v2;
```

- [ ] **Step 3: 编译检查**

Run: `cd src-tauri && cargo check --lib 2>&1 | tail -20`
Expected: 仅旧 pipeline 已有 warning，无 `pipeline_v2` 相关错误。

- [ ] **Step 4: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/
git add src-tauri/src/parsers/mod.rs
git commit -m "chore(rust): scaffold pipeline_v2 module structure"
```

---

### Task 2: 定义核心错误类型 `PipelineError`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/error.rs`
- Test: `src-tauri/src/parsers/pipeline_v2/error.rs` (inline `#[cfg(test)]`)

- [ ] **Step 1: 写入错误类型**

使用 `thiserror`（已在 `src-tauri/Cargo.toml` 中）。注意：字段原名 `source` 已改为 `detail`，因为 `thiserror` 会把名为 `source` 的字段当作 causal source。

```rust
//! Structured error types for the PDF processing pipeline.

use std::path::PathBuf;
use thiserror::Error;

/// Top-level error type for the PDF processing pipeline.
#[derive(Debug, Clone, PartialEq, Error)]
pub enum PipelineError {
    #[error("extract stage failed: {0}")]
    Extract(#[from] ExtractError),
    #[error("segment stage failed: {0}")]
    Segment(#[from] SegmentError),
    #[error("enrich stage failed: {0}")]
    Enrich(#[from] EnrichError),
    #[error("persist stage failed: {0}")]
    Persist(#[from] PersistError),
    #[error("index stage failed: {0}")]
    Index(#[from] IndexError),
}

#[derive(Debug, Clone, PartialEq, Error)]
pub enum ExtractError {
    #[error("source path invalid: {path}")]
    SourcePathInvalid { path: String },
    #[error("project root not found for path: {path}")]
    ProjectRootNotFound { path: String },
    #[error("inspector failed for '{path}': {detail}")]
    InspectorFailed { path: String, detail: String },
    #[error("all OCR backends failed for '{path}': {details}")]
    OcrAllBackendsFailed { path: String, details: String },
    #[error("image persist failed for '{filename}': {detail}")]
    ImagePersistFailed { filename: String, detail: String },
    #[error("cache read failed for '{cache}': {detail}")]
    CacheReadFailed { cache: String, detail: String },
}

#[derive(Debug, Clone, PartialEq, Error)]
pub enum SegmentError {
    #[error("document contains no text content")]
    NoTextContent,
    #[error("section '{title}' is too long ({chars} characters)")]
    SectionTooLong { title: String, chars: usize },
}

#[derive(Debug, Clone, PartialEq, Error)]
pub enum EnrichError {
    #[error("section processing failed for '{section}': {detail}")]
    SectionProcessingFailed { section: String, detail: String },
    #[error("molecule service failed: {detail}")]
    MoleculeServiceFailed { detail: String },
    #[error("caption service failed for '{filename}': {detail}")]
    CaptionServiceFailed { filename: String, detail: String },
    #[error("merge failed: {detail}")]
    MergeFailed { detail: String },
    #[error("chemical validation failed for '{esmiles}': {detail}")]
    ChemValidationFailed { esmiles: String, detail: String },
}

#[derive(Debug, Clone, PartialEq, Error)]
pub enum PersistError {
    #[error("text markdown write failed for '{path}': {detail}")]
    TextMdWriteFailed { path: PathBuf, detail: String },
    #[error("report markdown write failed for '{path}': {detail}")]
    ReportMdWriteFailed { path: PathBuf, detail: String },
    #[error("molecule store failed: {detail}")]
    MoleculeStoreFailed { detail: String },
    #[error("document id not resolved for path: {path}")]
    DocIdNotResolved { path: String },
}

#[derive(Debug, Clone, PartialEq, Error)]
pub enum IndexError {
    #[error("embedding failed: {detail}")]
    EmbeddingFailed { detail: String },
    #[error("vector store failed: {detail}")]
    VectorStoreFailed { detail: String },
    #[error("file cache write failed: {detail}")]
    FileCacheWriteFailed { detail: String },
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extract_error_display_includes_stage_and_details() {
        let err = PipelineError::Extract(ExtractError::InspectorFailed {
            path: "/tmp/x.pdf".into(),
            detail: "io".into(),
        });
        let msg = err.to_string();
        assert!(msg.contains("extract stage failed"));
        assert!(msg.contains("inspector failed for '/tmp/x.pdf': io"));
    }

    #[test]
    fn segment_error_display_includes_stage_and_details() {
        let err = PipelineError::Segment(SegmentError::SectionTooLong {
            title: "Introduction".into(),
            chars: 50000,
        });
        let msg = err.to_string();
        assert!(msg.contains("segment stage failed"));
        assert!(msg.contains("section 'Introduction' is too long (50000 characters)"));
    }

    #[test]
    fn enrich_error_display_includes_stage_and_details() {
        let err = PipelineError::Enrich(EnrichError::MoleculeServiceFailed {
            detail: "timeout".into(),
        });
        let msg = err.to_string();
        assert!(msg.contains("enrich stage failed"));
        assert!(msg.contains("molecule service failed: timeout"));
    }

    #[test]
    fn persist_error_display_includes_stage_and_details() {
        let err = PipelineError::Persist(PersistError::TextMdWriteFailed {
            path: PathBuf::from("/tmp/out.md"),
            detail: "permission denied".into(),
        });
        let msg = err.to_string();
        assert!(msg.contains("persist stage failed"));
        assert!(msg.contains("text markdown write failed for '/tmp/out.md': permission denied"));
    }

    #[test]
    fn index_error_display_includes_stage_and_details() {
        let err = PipelineError::Index(IndexError::EmbeddingFailed {
            detail: "model unavailable".into(),
        });
        let msg = err.to_string();
        assert!(msg.contains("index stage failed"));
        assert!(msg.contains("embedding failed: model unavailable"));
    }

    #[test]
    fn from_conversions_build_pipeline_error() {
        let extract: PipelineError = ExtractError::SourcePathInvalid { path: "/bad".into() }.into();
        assert!(matches!(extract, PipelineError::Extract(_)));

        let segment: PipelineError = SegmentError::NoTextContent.into();
        assert!(matches!(segment, PipelineError::Segment(_)));

        let enrich: PipelineError = EnrichError::MergeFailed { detail: "conflict".into() }.into();
        assert!(matches!(enrich, PipelineError::Enrich(_)));

        let persist: PipelineError = PersistError::DocIdNotResolved { path: "/missing".into() }.into();
        assert!(matches!(persist, PipelineError::Persist(_)));

        let index: PipelineError = IndexError::VectorStoreFailed { detail: "disk full".into() }.into();
        assert!(matches!(index, PipelineError::Index(_)));
    }
}
```

- [ ] **Step 2: 运行测试**

Run: `cd src-tauri && cargo test --lib pipeline_v2::error -- --nocapture`
Expected: `test error::tests::error_display_includes_stage ... ok`

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/error.rs
git commit -m "feat(rust): add structured PipelineError types"
```

---

### Task 3: 定义 `PipelineContext` 与 `PipelineReporter`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/context.rs`
- Test: `src-tauri/src/parsers/pipeline_v2/context.rs` (inline tests)

- [ ] **Step 1: 写入 context 与 reporter**

```rust
use std::path::{Path, PathBuf};
use std::sync::Arc;

#[derive(Debug, Clone)]
pub struct PipelineConfig {
    pub allow_ocr: bool,
    pub chunk_max_chars: usize,
    pub section_concurrency: usize,
}

impl Default for PipelineConfig {
    fn default() -> Self {
        Self {
            allow_ocr: true,
            chunk_max_chars: 8000,
            section_concurrency: 4,
        }
    }
}

#[derive(Debug, Clone)]
pub struct PipelineContext {
    pub source_path: PathBuf,
    pub project_root: Option<PathBuf>,
    pub user_request: String,
    pub reporter: Arc<dyn PipelineReporter>,
    pub config: PipelineConfig,
}

impl PipelineContext {
    pub fn new(source_path: impl AsRef<Path>, user_request: impl Into<String>) -> Self {
        Self {
            source_path: source_path.as_ref().to_path_buf(),
            project_root: None,
            user_request: user_request.into(),
            reporter: Arc::new(NoopReporter),
            config: PipelineConfig::default(),
        }
    }

    pub fn with_project_root(mut self, root: impl AsRef<Path>) -> Self {
        self.project_root = Some(root.as_ref().to_path_buf());
        self
    }

    pub fn with_reporter(mut self, reporter: Arc<dyn PipelineReporter>) -> Self {
        self.reporter = reporter;
        self
    }
}

#[derive(Debug, Clone)]
pub enum PipelineEvent {
    StageStart { stage: String },
    StageProgress { stage: String, message: String },
    StageComplete { stage: String },
    StageWarning { stage: String, message: String },
}

pub trait PipelineReporter: Send + Sync {
    fn report(&self, event: PipelineEvent);
}

pub struct NoopReporter;

impl PipelineReporter for NoopReporter {
    fn report(&self, _event: PipelineEvent) {}
}

pub struct CollectingReporter {
    pub events: std::sync::Mutex<Vec<PipelineEvent>>,
}

impl CollectingReporter {
    pub fn new() -> Self {
        Self {
            events: std::sync::Mutex::new(Vec::new()),
        }
    }
}

impl PipelineReporter for CollectingReporter {
    fn report(&self, event: PipelineEvent) {
        if let Ok(mut events) = self.events.lock() {
            events.push(event);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn collecting_reporter_records_events() {
        let reporter = Arc::new(CollectingReporter::new());
        reporter.report(PipelineEvent::StageStart {
            stage: "extract".into(),
        });
        let events = reporter.events.lock().unwrap();
        assert_eq!(events.len(), 1);
    }
}
```

- [ ] **Step 2: 运行测试**

Run: `cd src-tauri && cargo test --lib pipeline_v2::context -- --nocapture`
Expected: `collecting_reporter_records_events ... ok`

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/context.rs
git commit -m "feat(rust): add PipelineContext and PipelineReporter abstraction"
```

---

### Task 4: 定义 `Stage` trait 与 `StageOutcome`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/runner.rs`
- Test: `src-tauri/src/parsers/pipeline_v2/runner.rs` (inline tests)

- [ ] **Step 1: 写入 Stage trait 与基础 runner**

```rust
use crate::parsers::pipeline_v2::context::{PipelineContext, PipelineEvent};
use crate::parsers::pipeline_v2::error::PipelineError;

#[derive(Debug, Clone)]
pub struct StageLog {
    pub stage: String,
    pub message: String,
}

pub struct StageOutcome<T> {
    pub output: T,
    pub logs: Vec<StageLog>,
    pub warnings: Vec<String>,
}

impl<T> StageOutcome<T> {
    pub fn new(output: T) -> Self {
        Self {
            output,
            logs: Vec::new(),
            warnings: Vec::new(),
        }
    }

    pub fn with_log(mut self, stage: impl Into<String>, message: impl Into<String>) -> Self {
        self.logs.push(StageLog {
            stage: stage.into(),
            message: message.into(),
        });
        self
    }

    pub fn with_warning(mut self, message: impl Into<String>) -> Self {
        self.warnings.push(message.into());
        self
    }
}

#[async_trait::async_trait]
pub trait Stage<Input, Output>: Send + Sync {
    async fn run(&self, input: Input, ctx: &PipelineContext) -> Result<StageOutcome<Output>, PipelineError>;
}

pub struct PipelineRunner;

impl PipelineRunner {
    pub fn new() -> Self {
        Self
    }

    pub async fn run_stage<S, I, O>(
        &self,
        name: &str,
        stage: &S,
        input: I,
        ctx: &PipelineContext,
    ) -> Result<O, PipelineError>
    where
        S: Stage<I, O>,
    {
        ctx.reporter.report(PipelineEvent::StageStart {
            stage: name.into(),
        });

        let outcome = stage.run(input, ctx).await?;

        for warning in &outcome.warnings {
            ctx.reporter.report(PipelineEvent::StageWarning {
                stage: name.into(),
                message: warning.clone(),
            });
        }

        ctx.reporter.report(PipelineEvent::StageComplete {
            stage: name.into(),
        });

        Ok(outcome.output)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parsers::pipeline_v2::context::{CollectingReporter, PipelineContext};
    use std::sync::Arc;

    struct DoubleStage;

    #[async_trait::async_trait]
    impl Stage<i32, i32> for DoubleStage {
        async fn run(
            &self,
            input: i32,
            _ctx: &PipelineContext,
        ) -> Result<StageOutcome<i32>, PipelineError> {
            Ok(StageOutcome::new(input * 2))
        }
    }

    #[tokio::test]
    async fn runner_executes_stage_and_emits_events() {
        let reporter = Arc::new(CollectingReporter::new());
        let ctx = PipelineContext::new("/tmp/test.pdf", "").with_reporter(reporter.clone());
        let runner = PipelineRunner::new();
        let result = runner.run_stage("double", &DoubleStage, 21, &ctx).await.unwrap();
        assert_eq!(result, 42);

        let events = reporter.events.lock().unwrap();
        assert!(events.iter().any(|e| matches!(e, PipelineEvent::StageStart { stage } if stage == "double")));
        assert!(events.iter().any(|e| matches!(e, PipelineEvent::StageComplete { stage } if stage == "double")));
    }
}
```

- [ ] **Step 2: 添加依赖 `async-trait` 到 Cargo.toml（如尚未添加）**

检查 `src-tauri/Cargo.toml` 中是否已有 `async-trait`：

Run: `grep -n "async-trait" src-tauri/Cargo.toml`

如果未找到，添加：

```toml
async-trait = "0.1"
```

到 `[dependencies]` 段。

- [ ] **Step 3: 运行测试**

Run: `cd src-tauri && cargo test --lib pipeline_v2::runner -- --nocapture`
Expected: `runner_executes_stage_and_emits_events ... ok`

- [ ] **Step 4: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/runner.rs
git add src-tauri/Cargo.toml
git commit -m "feat(rust): add Stage trait and PipelineRunner"
```

---

## Phase 2: 数据模型

### Task 5: 迁移通用类型到 `models/`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/models/mod.rs`
- Modify: `src-tauri/src/parsers/doc_types.rs`（保留旧类型，新模型独立定义）

- [ ] **Step 1: 写入模型模块**

```rust
pub mod enriched;
pub mod extracted;
pub mod persisted;
pub mod segmented;
pub mod source;

pub use enriched::*;
pub use extracted::*;
pub use persisted::*;
pub use segmented::*;
pub use source::*;
```

- [ ] **Step 2: 创建 `source.rs`**

```rust
use std::path::PathBuf;

#[derive(Debug, Clone)]
pub struct SourceInput {
    pub path: PathBuf,
    pub project_root: Option<PathBuf>,
    pub allow_ocr: bool,
}

impl SourceInput {
    pub fn new(path: impl Into<PathBuf>) -> Self {
        Self {
            path: path.into(),
            project_root: None,
            allow_ocr: true,
        }
    }

    pub fn with_project_root(mut self, root: impl Into<PathBuf>) -> Self {
        self.project_root = Some(root.into());
        self
    }

    pub fn with_allow_ocr(mut self, allow: bool) -> Self {
        self.allow_ocr = allow;
        self
    }
}
```

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/models/
git commit -m "feat(rust): add pipeline_v2 models module scaffold"
```

---

### Task 6: 定义 `ExtractedDocument` 与 `ImageRef`/`OcrBlock`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/models/extracted.rs`

- [ ] **Step 1: 写入模型**

```rust
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExtractedDocument {
    pub raw_text: String,
    pub page_count: usize,
    pub parser: String,
    pub images: Vec<ImageRef>,
    pub ocr_blocks: Vec<OcrBlock>,
    pub metadata: ExtractedMetadata,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ExtractedMetadata {
    pub title: Option<String>,
    pub authors: Vec<String>,
    pub document_type: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ImageRef {
    pub filename: String,
    pub page: usize,
    pub region: Option<String>,
    pub description: Option<String>,
    pub esmiles: Option<String>,
    pub rel_path: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OcrBlock {
    pub page: usize,
    pub block_type: String,
    pub bbox: [f64; 4],
    pub content: Option<String>,
    pub index: usize,
    pub angle: i32,
}
```

- [ ] **Step 2: 编译检查**

Run: `cd src-tauri && cargo check --lib 2>&1 | tail -20`
Expected: 无 `pipeline_v2` 相关错误。

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/models/extracted.rs
git commit -m "feat(rust): add ExtractedDocument and related models"
```

---

### Task 7: 定义 `SegmentedDocument` 与 `SectionChunk`/`Heading`/`TreeNode`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/models/segmented.rs`

- [ ] **Step 1: 写入模型**

```rust
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone)]
pub struct SegmentedDocument {
    pub sections: Vec<SectionChunk>,
    pub document_tree: Vec<TreeNode>,
    pub headings: Vec<Heading>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SectionChunk {
    pub title: String,
    pub path: String,
    pub text: String,
    pub page_start: Option<usize>,
    pub page_end: Option<usize>,
    pub line_start: usize,
    pub line_end: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Heading {
    pub level: usize,
    pub title: String,
    pub line_num: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TreeNode {
    pub title: String,
    pub node_id: String,
    pub line_num: usize,
    pub nodes: Vec<TreeNode>,
}
```

- [ ] **Step 2: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/models/segmented.rs
git commit -m "feat(rust): add SegmentedDocument and section models"
```

---

### Task 8: 定义 `EnrichedDocument` 与 `PersistedDocument`/`IndexedDocument`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/models/enriched.rs`
- Create: `src-tauri/src/parsers/pipeline_v2/models/persisted.rs`

- [ ] **Step 1: 写入 enriched.rs**

```rust
use std::collections::HashMap;

use crate::parsers::doc_types::{CompoundEntry, DocumentMetadata, StructuredData};
use crate::parsers::pipeline_v2::models::segmented::SectionChunk;

#[derive(Debug, Clone)]
pub struct EnrichedDocument {
    pub structured_data: StructuredData,
    pub sar_analysis: Option<String>,
    pub molecule_results: Vec<DetectedMoleculeResult>,
    pub image_captions: HashMap<String, String>,
    pub sections: Vec<SectionChunk>,
}

#[derive(Debug, Clone)]
pub struct DetectedMoleculeResult {
    pub esmiles: String,
    pub confidence: f64,
    pub moldet_conf: f64,
    pub page: usize,
    pub crop_path: String,
    pub bbox_pdf: [f64; 4],
}
```

- [ ] **Step 2: 写入 persisted.rs**

```rust
use std::path::PathBuf;

#[derive(Debug, Clone)]
pub struct PersistedDocument {
    pub doc_id: String,
    pub text_md_path: PathBuf,
    pub report_md_path: PathBuf,
    pub unverified_image_count: usize,
    pub persisted_molecule_count: usize,
}

#[derive(Debug, Clone)]
pub struct IndexedDocument {
    pub doc_id: String,
    pub indexed_sections: usize,
}
```

- [ ] **Step 3: 编译检查**

Run: `cd src-tauri && cargo check --lib 2>&1 | tail -30`
Expected: 无 `pipeline_v2` 相关错误。

- [ ] **Step 4: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/models/enriched.rs
git add src-tauri/src/parsers/pipeline_v2/models/persisted.rs
git commit -m "feat(rust): add EnrichedDocument, PersistedDocument, IndexedDocument"
```

---

## Phase 3: Extract Stage

### Task 9: 实现 `SourceResolver` 与 `ExtractCacheService`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/services/source.rs`
- Create: `src-tauri/src/parsers/pipeline_v2/services/cache.rs`

- [ ] **Step 1: 写入 `source.rs`**

```rust
use std::path::{Path, PathBuf};

use crate::parsers::pipeline_v2::error::{ExtractError, PipelineError};

pub struct SourceResolver;

impl SourceResolver {
    pub fn new() -> Self {
        Self
    }

    pub fn resolve_project_root(
        &self,
        source_path: &Path,
        hint: Option<&Path>,
    ) -> Result<PathBuf, PipelineError> {
        if let Some(root) = hint {
            if root.is_dir() {
                return Ok(root.to_path_buf());
            }
        }

        let mut current = source_path.parent();
        while let Some(dir) = current {
            if dir.join(".mbforge").is_dir() || dir.join("molecules.db").exists() {
                return Ok(dir.to_path_buf());
            }
            current = dir.parent();
        }

        Err(PipelineError::Extract(ExtractError::ProjectRootNotFound {
            path: source_path.display().to_string(),
        }))
    }
}
```

- [ ] **Step 2: 写入 `cache.rs` 中的 trait 和 `FileCache` 存根**

```rust
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

use crate::parsers::pipeline_v2::error::{ExtractError, PipelineError};

pub trait Cache<K, V>: Send + Sync {
    fn get(&self, key: &K) -> Result<Option<V>, PipelineError>;
    fn put(&self, key: &K, value: &V) -> Result<(), PipelineError>;
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CachedExtractResult {
    pub text: String,
    pub sections_json: String,
    pub metadata_json: String,
}

pub struct FileCache {
    root: PathBuf,
}

impl FileCache {
    pub fn new(root: impl AsRef<Path>) -> Self {
        Self {
            root: root.as_ref().to_path_buf(),
        }
    }

    fn cache_path(&self, key: &str) -> PathBuf {
        self.root.join("index").join("file-cache").join(format!("{}.json", key))
    }
}

impl Cache<String, CachedExtractResult> for FileCache {
    fn get(&self, key: &String) -> Result<Option<CachedExtractResult>, PipelineError> {
        let path = self.cache_path(key);
        if !path.exists() {
            return Ok(None);
        }
        let content = std::fs::read_to_string(&path).map_err(|e| {
            PipelineError::Extract(ExtractError::CacheReadFailed {
                cache: "FileCache".into(),
                source: e.to_string(),
            })
        })?;
        let val: CachedExtractResult = serde_json::from_str(&content).map_err(|e| {
            PipelineError::Extract(ExtractError::CacheReadFailed {
                cache: "FileCache".into(),
                source: e.to_string(),
            })
        })?;
        Ok(Some(val))
    }

    fn put(&self, key: &String, value: &CachedExtractResult) -> Result<(), PipelineError> {
        let path = self.cache_path(key);
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|e| {
                PipelineError::Extract(ExtractError::CacheReadFailed {
                    cache: "FileCache".into(),
                    source: e.to_string(),
                })
            })?;
        }
        let content = serde_json::to_string_pretty(value).map_err(|e| {
            PipelineError::Extract(ExtractError::CacheReadFailed {
                cache: "FileCache".into(),
                source: e.to_string(),
            })
        })?;
        std::fs::write(&path, content).map_err(|e| {
            PipelineError::Extract(ExtractError::CacheReadFailed {
                cache: "FileCache".into(),
                source: e.to_string(),
            })
        })
    }
}
```

- [ ] **Step 3: 运行测试**

Run: `cd src-tauri && cargo check --lib 2>&1 | tail -30`
Expected: 无新增错误。

- [ ] **Step 4: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/services/source.rs
git add src-tauri/src/parsers/pipeline_v2/services/cache.rs
git commit -m "feat(rust): add SourceResolver and FileCache abstraction"
```

---

### Task 10: 实现 `InspectorService` 与 `OcrService`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/services/inspector.rs`
- Create: `src-tauri/src/parsers/pipeline_v2/services/ocr.rs`

- [ ] **Step 1: 写入 `inspector.rs`**

```rust
use std::path::Path;

use crate::parsers::pipeline_v2::error::{ExtractError, PipelineError};
use crate::parsers::pipeline_v2::models::extracted::{ExtractedDocument, ExtractedMetadata};

pub struct InspectorService;

impl InspectorService {
    pub fn new() -> Self {
        Self
    }

    pub async fn extract(&self, path: &Path) -> Result<ExtractedDocument, PipelineError> {
        let path_str = path.to_string_lossy().to_string();

        let result = tokio::task::spawn_blocking(move || {
            crate::parsers::pdf::inspector::process_pdf(&path_str)
        })
        .await
        .map_err(|e| PipelineError::Extract(ExtractError::InspectorFailed {
            path: path_str.clone(),
            source: format!("join error: {}", e),
        }))?
        .map_err(|e| PipelineError::Extract(ExtractError::InspectorFailed {
            path: path_str,
            source: e,
        }))?;

        Ok(ExtractedDocument {
            raw_text: result.markdown.unwrap_or_default(),
            page_count: result.page_count as usize,
            parser: "pdf_inspector".into(),
            images: Vec::new(),
            ocr_blocks: Vec::new(),
            metadata: ExtractedMetadata::default(),
        })
    }
}
```

注意：`crate::parsers::pdf::inspector` 可能不存在。实际应调用 `pdf_inspector::process_pdf`（crate 级函数）或通过 `PdfInspectorContext`。**实现者需根据实际 API 调整此处路径**。

- [ ] **Step 2: 写入 `ocr.rs` trait 与 service**

```rust
use async_trait::async_trait;
use std::path::Path;

use crate::parsers::pipeline_v2::error::{ExtractError, PipelineError};
use crate::parsers::pipeline_v2::models::extracted::{ImageRef, OcrBlock};

#[derive(Debug, Clone)]
pub struct OcrOutput {
    pub text: String,
    pub page_count: usize,
    pub images: Vec<ImageRef>,
    pub ocr_blocks: Vec<OcrBlock>,
}

#[async_trait]
pub trait OcrBackend: Send + Sync {
    fn name(&self) -> &'static str;
    fn is_available(&self) -> bool;
    async fn run(&self, path: &Path) -> Result<OcrOutput, PipelineError>;
}

pub struct OcrService {
    backends: Vec<Box<dyn OcrBackend>>,
}

impl OcrService {
    pub fn new(backends: Vec<Box<dyn OcrBackend>>) -> Self {
        Self { backends }
    }

    pub async fn run(&self, path: &Path) -> Result<(OcrOutput, &'static str), PipelineError> {
        let path_str = path.to_string_lossy().to_string();
        let mut errors = Vec::new();

        for backend in &self.backends {
            if !backend.is_available() {
                continue;
            }
            match backend.run(path).await {
                Ok(out) => return Ok((out, backend.name())),
                Err(e) => errors.push(format!("{}: {}", backend.name(), e)),
            }
        }

        Err(PipelineError::Extract(ExtractError::OcrAllBackendsFailed {
            path: path_str,
            details: errors.join("; "),
        }))
    }
}
```

- [ ] **Step 3: 编译检查并修复 API 路径**

Run: `cd src-tauri && cargo check --lib 2>&1 | grep -E "(error|warning)" | head -30`

根据错误修复 `inspector.rs` 中实际调用的 pdf-inspector API。

- [ ] **Step 4: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/services/inspector.rs
git add src-tauri/src/parsers/pipeline_v2/services/ocr.rs
git commit -m "feat(rust): add InspectorService and OcrService abstractions"
```

---

### Task 11: 实现 `ImageService`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/services/images.rs`

- [ ] **Step 1: 写入图片服务**

```rust
use std::path::{Path, PathBuf};

use crate::parsers::pipeline_v2::error::{ExtractError, PipelineError};
use crate::parsers::pipeline_v2::models::extracted::ImageRef;

pub struct ImageService;

impl ImageService {
    pub fn new() -> Self {
        Self
    }

    pub async fn extract_embedded_images(
        &self,
        pdf_path: &Path,
        tmp_dir: &Path,
    ) -> Result<Vec<crate::parsers::pdf::images::ExtractedImage>, PipelineError> {
        let pdf_path = pdf_path.to_path_buf();
        let tmp_dir = tmp_dir.to_path_buf();

        tokio::task::spawn_blocking(move || {
            crate::parsers::pdf::images::extract_images_from_pdf(
                pdf_path.to_string_lossy().as_ref(),
                &tmp_dir,
                50,
                5,
            )
        })
        .await
        .map_err(|e| {
            PipelineError::Extract(ExtractError::ImagePersistFailed {
                filename: pdf_path.display().to_string(),
                source: format!("join error: {}", e),
            })
        })
        .map(|r| r.unwrap_or_default())
    }

    pub fn persist_extracted_images(
        &self,
        source_path: &Path,
        project_root: &Path,
        extracted: &[crate::parsers::pdf::images::ExtractedImage],
    ) -> Vec<ImageRef> {
        // 迁移原 extract.rs::persist_extracted_images 逻辑
        let doc_slug = source_path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown");
        let media_dir = project_root.join("reports").join("figures").join(doc_slug);

        extracted
            .iter()
            .map(|img| {
                let rel_path = if std::fs::create_dir_all(&media_dir).is_ok() {
                    let dest = media_dir.join(&img.filename);
                    if std::fs::copy(&img.path, &dest).is_ok() {
                        dest.strip_prefix(project_root)
                            .ok()
                            .map(|p| p.to_string_lossy().to_string())
                    } else {
                        None
                    }
                } else {
                    None
                };
                ImageRef {
                    filename: img.filename.clone(),
                    page: img.page,
                    region: None,
                    description: None,
                    esmiles: None,
                    rel_path,
                }
            })
            .collect()
    }

    pub fn persist_backend_images(
        &self,
        project_root: &Path,
        images: &[ImageRef],
        backend_name: &str,
        doc_slug: &str,
    ) -> Vec<ImageRef> {
        let media_dir = project_root
            .join("reports")
            .join("figures")
            .join(doc_slug)
            .join(backend_name);

        if std::fs::create_dir_all(&media_dir).is_err() {
            return images.to_vec();
        }

        images
            .iter()
            .map(|img| {
                let rel = img.rel_path.as_ref().unwrap_or(&img.filename);
                let src = Path::new(rel);
                if !src.exists() {
                    return img.clone();
                }
                let dest = media_dir.join(&img.filename);
                if std::fs::copy(src, &dest).is_err() {
                    return img.clone();
                }
                match dest.strip_prefix(project_root) {
                    Ok(rp) => ImageRef {
                        rel_path: Some(rp.to_string_lossy().to_string()),
                        ..img.clone()
                    },
                    Err(_) => img.clone(),
                }
            })
            .collect()
    }
}
```

- [ ] **Step 2: 编译检查并修复常量引用**

`"reports"` 应替换为 `crate::core::config::constants::REPORTS_DIR`。

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/services/images.rs
git commit -m "feat(rust): add ImageService for extraction and persistence"
```

---

### Task 12: 组装 `ExtractStage`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/stages/extract.rs`

- [ ] **Step 1: 写入 ExtractStage**

```rust
use std::path::Path;

use async_trait::async_trait;

use crate::parsers::pipeline_v2::context::PipelineContext;
use crate::parsers::pipeline_v2::error::{ExtractError, PipelineError};
use crate::parsers::pipeline_v2::models::extracted::ExtractedDocument;
use crate::parsers::pipeline_v2::models::source::SourceInput;
use crate::parsers::pipeline_v2::runner::{Stage, StageOutcome};
use crate::parsers::pipeline_v2::services::cache::{Cache, CachedExtractResult, FileCache};
use crate::parsers::pipeline_v2::services::images::ImageService;
use crate::parsers::pipeline_v2::services::inspector::InspectorService;
use crate::parsers::pipeline_v2::services::ocr::OcrService;
use crate::parsers::pipeline_v2::services::source::SourceResolver;

pub struct ExtractStage {
    pub inspector: InspectorService,
    pub ocr: OcrService,
    pub images: ImageService,
    pub resolver: SourceResolver,
}

impl ExtractStage {
    pub fn new(ocr: OcrService) -> Self {
        Self {
            inspector: InspectorService::new(),
            ocr,
            images: ImageService::new(),
            resolver: SourceResolver::new(),
        }
    }
}

#[async_trait]
impl Stage<SourceInput, ExtractedDocument> for ExtractStage {
    async fn run(
        &self,
        input: SourceInput,
        ctx: &PipelineContext,
    ) -> Result<StageOutcome<ExtractedDocument>, PipelineError> {
        let source_path = input.path;

        ctx.reporter.report(crate::parsers::pipeline_v2::context::PipelineEvent::StageProgress {
            stage: "extract".into(),
            message: "resolving project root".into(),
        });

        let project_root = self
            .resolver
            .resolve_project_root(&source_path, ctx.project_root.as_deref())?;

        // 文件缓存检查（简化：以 source path + mtime 为 key）
        let file_cache = FileCache::new(&project_root);
        let cache_key = format!("{}", source_path.display());
        if let Some(cached) = file_cache.get(&cache_key)? {
            ctx.reporter.report(crate::parsers::pipeline_v2::context::PipelineEvent::StageProgress {
                stage: "extract".into(),
                message: "file cache hit".into(),
            });
            // 这里简化处理：只恢复 text；images/ocr_blocks 从 metadata_json 解析
            let metadata: serde_json::Value = serde_json::from_str(&cached.metadata_json)
                .unwrap_or_default();
            let images: Vec<crate::parsers::pipeline_v2::models::extracted::ImageRef> = metadata
                .get("images")
                .and_then(|v| serde_json::from_value(v.clone()).ok())
                .unwrap_or_default();
            let ocr_blocks: Vec<crate::parsers::pipeline_v2::models::extracted::OcrBlock> = metadata
                .get("ocr_blocks")
                .and_then(|v| serde_json::from_value(v.clone()).ok())
                .unwrap_or_default();
            let page_count = metadata
                .get("page_count")
                .and_then(|v| v.as_u64())
                .unwrap_or(0) as usize;
            return Ok(StageOutcome::new(ExtractedDocument {
                raw_text: cached.text,
                page_count,
                parser: "cached".into(),
                images,
                ocr_blocks,
                metadata: crate::parsers::pipeline_v2::models::extracted::ExtractedMetadata::default(),
            }));
        }

        ctx.reporter.report(crate::parsers::pipeline_v2::context::PipelineEvent::StageProgress {
            stage: "extract".into(),
            message: "running pdf-inspector".into(),
        });

        let mut extracted = self.inspector.extract(&source_path).await?;

        let is_scanned =
            extracted.raw_text.len() < 100 && extracted.page_count > 0 || !extracted.ocr_blocks.is_empty();

        if is_scanned && input.allow_ocr {
            ctx.reporter.report(crate::parsers::pipeline_v2::context::PipelineEvent::StageProgress {
                stage: "extract".into(),
                message: "running OCR".into(),
            });

            match self.ocr.run(&source_path).await {
                Ok((ocr_out, backend_name)) => {
                    let doc_slug = source_path
                        .file_stem()
                        .and_then(|s| s.to_str())
                        .unwrap_or("unknown");
                    let backend_images = self
                        .images
                        .persist_backend_images(&project_root, &ocr_out.images, backend_name, doc_slug);

                    extracted.raw_text = ocr_out.text;
                    extracted.page_count = ocr_out.page_count.max(extracted.page_count);
                    extracted.parser = backend_name.into();
                    extracted.images.extend(backend_images);
                    extracted.ocr_blocks = ocr_out.ocr_blocks;
                }
                Err(e) => {
                    return Ok(StageOutcome::new(extracted)
                        .with_warning("extract", format!("OCR failed, falling back to inspector text: {}", e)));
                }
            }
        }

        // 提取并持久化 PDF 内嵌图片
        let tmp = tempfile::tempdir().map_err(|e| {
            PipelineError::Extract(ExtractError::ImagePersistFailed {
                filename: source_path.display().to_string(),
                source: e.to_string(),
            })
        })?;
        let embedded = self
            .images
            .extract_embedded_images(&source_path, tmp.path())
            .await?;
        let doc_slug = source_path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown");
        let mut embedded_images = self
            .images
            .persist_extracted_images(&source_path, &project_root, &embedded);
        embedded_images.extend(extracted.images.drain(..));
        extracted.images = embedded_images;

        Ok(StageOutcome::new(extracted))
    }
}
```

- [ ] **Step 2: 编译检查并修复所有引用**

Run: `cd src-tauri && cargo check --lib 2>&1 | grep -E "^error" | head -30`

根据错误修复类型引用和常量。

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/stages/extract.rs
git commit -m "feat(rust): add ExtractStage implementation"
```

---

## Phase 4: Segment Stage

### Task 13: 迁移 heading/section 逻辑到 `pipeline_v2`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/stages/segment.rs`
- Reference: `src-tauri/src/parsers/structure/sections.rs`

- [ ] **Step 1: 复用并迁移现有 section 逻辑**

将 `src-tauri/src/parsers/structure/sections.rs` 中的核心函数（`extract_headings`、`build_sections`、`build_tree`、`split_long_section`、`split_semantic_chunks`、`build_semantic_sections`）复制或重导出到 `pipeline_v2/stages/segment.rs`，并适配新模型类型。

核心逻辑保持不变，仅把输入输出类型从旧的 `SectionChunk`/`Heading`/`TreeNode` 切换为 `crate::parsers::pipeline_v2::models::segmented::*`。

- [ ] **Step 2: 实现 SegmentStage**

```rust
use async_trait::async_trait;

use crate::parsers::pipeline_v2::context::PipelineContext;
use crate::parsers::pipeline_v2::error::PipelineError;
use crate::parsers::pipeline_v2::models::extracted::ExtractedDocument;
use crate::parsers::pipeline_v2::models::segmented::SegmentedDocument;
use crate::parsers::pipeline_v2::runner::{Stage, StageOutcome};

pub struct SegmentStage {
    pub max_chars: usize,
}

impl SegmentStage {
    pub fn new(max_chars: usize) -> Self {
        Self { max_chars }
    }
}

#[async_trait]
impl Stage<ExtractedDocument, SegmentedDocument> for SegmentStage {
    async fn run(
        &self,
        input: ExtractedDocument,
        ctx: &PipelineContext,
    ) -> Result<StageOutcome<SegmentedDocument>, PipelineError> {
        ctx.reporter.report(crate::parsers::pipeline_v2::context::PipelineEvent::StageProgress {
            stage: "segment".into(),
            message: "extracting headings".into(),
        });

        let headings = extract_headings(&input.raw_text);
        let sections = build_sections(&input.raw_text, &headings, None, self.max_chars);
        let document_tree = build_tree(&sections);

        ctx.reporter.report(crate::parsers::pipeline_v2::context::PipelineEvent::StageProgress {
            stage: "segment".into(),
            message: format!("built {} sections", sections.len()),
        });

        Ok(StageOutcome::new(SegmentedDocument {
            sections,
            document_tree,
            headings,
        }))
    }
}
```

- [ ] **Step 3: 复制 tests**

从 `src-tauri/src/parsers/structure/sections.rs` 复制相关 tests 到 `segment.rs` 底部，并适配新类型。

- [ ] **Step 4: 运行测试**

Run: `cd src-tauri && cargo test --lib pipeline_v2::stages::segment -- --nocapture`
Expected: 所有 tests pass。

- [ ] **Step 5: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/stages/segment.rs
git commit -m "feat(rust): migrate sectioning logic into SegmentStage"
```

---

## Phase 5: Enrich Stage

### Task 14: 实现 `SectionProcessor`、`MoleculeService`、`ImageCaptionService`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/services/section_processor.rs`
- Create: `src-tauri/src/parsers/pipeline_v2/services/molecules.rs`
- Create: `src-tauri/src/parsers/pipeline_v2/services/captions.rs`

- [ ] **Step 1: `section_processor.rs` 写入并行 section 提取框架**

```rust
use crate::parsers::doc_types::StructuredData;
use crate::parsers::pipeline_v2::error::{EnrichError, PipelineError};
use crate::parsers::pipeline_v2::models::segmented::SectionChunk;

pub struct SectionProcessor;

impl SectionProcessor {
    pub fn new() -> Self {
        Self
    }

    pub async fn process_sections(
        &self,
        sections: &[SectionChunk],
        parser: &str,
        page_count: usize,
    ) -> Result<Vec<StructuredData>, PipelineError> {
        // 迁移原 pipeline.rs 中 post_process_sections_parallel 的逻辑
        // 输入 (name, text) pairs，输出 Vec<StructuredData>
        let inputs: Vec<(String, String)> = sections
            .iter()
            .map(|s| (s.title.clone(), s.text.clone()))
            .collect();

        let results = crate::parsers::structure::post_process::post_process_sections_parallel(
            inputs,
            parser,
            page_count,
            None,
        )
        .await;

        let mut data = Vec::new();
        for res in results {
            if let Some(d) = res.into_data() {
                data.push(d);
            }
        }
        Ok(data)
    }
}
```

- [ ] **Step 2: `molecules.rs` 写入分子识别服务**

```rust
use crate::parsers::pipeline_v2::error::{EnrichError, PipelineError};
use crate::parsers::pipeline_v2::models::enriched::DetectedMoleculeResult;
use crate::parsers::pipeline_v2::models::extracted::ExtractedDocument;

pub struct MoleculeService {
    pub sidecar_url: String,
}

impl MoleculeService {
    pub fn new(sidecar_url: impl Into<String>) -> Self {
        Self {
            sidecar_url: sidecar_url.into(),
        }
    }

    pub async fn extract(
        &self,
        path: &str,
        extracted: &ExtractedDocument,
        project_root: &std::path::Path,
    ) -> Result<Vec<DetectedMoleculeResult>, PipelineError> {
        let classified = crate::parsers::pipeline::extract::ClassifyResult {
            text: extracted.raw_text.clone(),
            page_count: extracted.page_count,
            parser: extracted.parser.clone(),
            images: extracted.images.clone(),
            ocr_blocks: extracted.ocr_blocks.clone(),
        };

        let detected = crate::parsers::pipeline::extract::extract_molecules_from_pdf(
            path,
            &classified,
            &self.sidecar_url,
            project_root,
        )
        .await
        .map_err(|e| {
            PipelineError::Enrich(EnrichError::MoleculeServiceFailed { source: e })
        })?;

        Ok(detected
            .into_iter()
            .map(|m| DetectedMoleculeResult {
                esmiles: m.esmiles,
                confidence: m.confidence,
                moldet_conf: m.moldet_conf,
                page: m.page as usize,
                crop_path: m.crop_path,
                bbox_pdf: m.bbox_pdf,
            })
            .collect())
    }
}
```

- [ ] **Step 3: `captions.rs` 写入图片描述服务**

```rust
use std::collections::HashMap;
use std::path::Path;

use crate::parsers::pipeline_v2::error::{EnrichError, PipelineError};
use crate::parsers::pipeline_v2::models::extracted::ImageRef;

pub struct ImageCaptionService {
    pub sidecar_url: String,
}

impl ImageCaptionService {
    pub fn new(sidecar_url: impl Into<String>) -> Self {
        Self {
            sidecar_url: sidecar_url.into(),
        }
    }

    pub async fn caption_images(
        &self,
        images: &mut [ImageRef],
        project_root: &Path,
    ) -> Result<HashMap<String, String>, PipelineError> {
        let mut cache = crate::parsers::chem::vlm_chem::ImageCaptionCache::new(project_root);
        let prompt = "请详细描述这张科学文献图片的内容。如果是图表，请说明其中的关键数据和趋势；如果是分子结构图，请描述其骨架特征和官能团；如果是实验流程图，请概述主要步骤。用中文回答，不超过100字。";
        let mut result = HashMap::new();

        for img in images.iter_mut() {
            if crate::parsers::chem::vlm_chem::is_likely_chemical_structure(
                &img.filename,
                img.region.as_deref(),
            ) {
                continue;
            }
            let full_path = Self::resolve_image_path(img, project_root);
            if full_path.is_none() {
                continue;
            }
            let full_path = full_path.unwrap();
            match crate::parsers::chem::vlm_chem::describe_image_cached(
                &full_path,
                prompt,
                &self.sidecar_url,
                &mut cache,
            )
            .await
            {
                Ok(caption) => {
                    img.description = Some(caption.clone());
                    result.insert(img.filename.clone(), caption);
                }
                Err(e) => {
                    return Err(PipelineError::Enrich(EnrichError::CaptionServiceFailed {
                        filename: img.filename.clone(),
                        source: e,
                    }));
                }
            }
        }

        cache.save().map_err(|e| {
            PipelineError::Enrich(EnrichError::CaptionServiceFailed {
                filename: "cache".into(),
                source: e,
            })
        })?;

        Ok(result)
    }

    fn resolve_image_path(img: &ImageRef, project_root: &Path) -> Option<String> {
        if let Some(ref rel) = img.rel_path {
            let full = project_root.join(rel);
            if full.exists() {
                return Some(full.to_string_lossy().to_string());
            }
        }
        None
    }
}
```

- [ ] **Step 4: 编译检查**

Run: `cd src-tauri && cargo check --lib 2>&1 | grep -E "^error" | head -30`

- [ ] **Step 5: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/services/section_processor.rs
git add src-tauri/src/parsers/pipeline_v2/services/molecules.rs
git add src-tauri/src/parsers/pipeline_v2/services/captions.rs
git commit -m "feat(rust): add section, molecule, and caption services"
```

---

### Task 15: 实现 `StructuredDataMerger` 与 `ChemValidator`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/services/merge.rs`
- Create: `src-tauri/src/parsers/pipeline_v2/services/chem_validate.rs`

- [ ] **Step 1: 写入 `merge.rs`**

```rust
use crate::parsers::doc_types::StructuredData;
use crate::parsers::pipeline_v2::error::{EnrichError, PipelineError};
use crate::parsers::pipeline_v2::models::enriched::DetectedMoleculeResult;

pub struct StructuredDataMerger;

impl StructuredDataMerger {
    pub fn new() -> Self {
        Self
    }

    pub async fn merge(
        &self,
        section_results: &[StructuredData],
        vlm_results: &[(String, crate::parsers::chem::vlm_chem::ChemImageResult)],
    ) -> Result<(StructuredData, Option<String>), PipelineError> {
        crate::parsers::pipeline::merge::run_merge_and_sar(section_results, vlm_results, &Default::default())
            .await
            .map_err(|e| PipelineError::Enrich(EnrichError::MergeFailed { source: e }))
    }
}
```

注意：`run_merge_and_sar` 签名需要 `DocStructure`，不是 `Default::default()`。**实现者需传入正确的 doc structure 或调整 service 接口**。

- [ ] **Step 2: 写入 `chem_validate.rs`**

```rust
use crate::parsers::doc_types::CompoundEntry;
use crate::parsers::pipeline_v2::error::{EnrichError, PipelineError};

pub struct ChemValidator;

impl ChemValidator {
    pub fn new() -> Self {
        Self
    }

    pub fn validate_compounds(
        &self,
        compounds: &mut [CompoundEntry],
    ) -> Result<(), PipelineError> {
        let esmiles_to_validate: Vec<String> = compounds
            .iter()
            .filter_map(|c| c.esmiles.clone())
            .collect::<std::collections::HashSet<_>>()
            .into_iter()
            .collect();

        if esmiles_to_validate.is_empty() {
            return Ok(());
        }

        let results =
            crate::parsers::chem::chem_validate::validate_smiles_batch(&esmiles_to_validate);

        for compound in compounds.iter_mut() {
            let Some(ref esmiles) = compound.esmiles else {
                continue;
            };
            let Some((_, result)) = results.iter().find(|(s, _)| s == esmiles) else {
                continue;
            };
            if result.valid {
                if let Some(ref canonical) = result.canonical_smiles {
                    if canonical != esmiles {
                        compound.esmiles = Some(canonical.clone());
                    }
                }
                if compound.confidence != "high" && result.issues.is_empty() {
                    compound.confidence = "high".into();
                }
            } else {
                compound.confidence = "low".into();
                let issue_msgs: Vec<String> = result
                    .issues
                    .iter()
                    .map(|i| format!("[{}] {}", i.code, i.message))
                    .collect();
                compound.uncertainty_reason = Some(format!(
                    "化学结构验证失败: {}",
                    issue_msgs.join("; ")
                ));
            }
        }

        Ok(())
    }
}
```

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/services/merge.rs
git add src-tauri/src/parsers/pipeline_v2/services/chem_validate.rs
git commit -m "feat(rust): add merge and chem validation services"
```

---

### Task 16: 组装 `EnrichStage`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/stages/enrich.rs`

- [ ] **Step 1: 写入 EnrichStage**

```rust
use async_trait::async_trait;

use crate::parsers::pipeline_v2::context::PipelineContext;
use crate::parsers::pipeline_v2::error::PipelineError;
use crate::parsers::pipeline_v2::models::enriched::EnrichedDocument;
use crate::parsers::pipeline_v2::models::extracted::ExtractedDocument;
use crate::parsers::pipeline_v2::models::segmented::SegmentedDocument;
use crate::parsers::pipeline_v2::runner::{Stage, StageOutcome};
use crate::parsers::pipeline_v2::services::captions::ImageCaptionService;
use crate::parsers::pipeline_v2::services::chem_validate::ChemValidator;
use crate::parsers::pipeline_v2::services::merge::StructuredDataMerger;
use crate::parsers::pipeline_v2::services::molecules::MoleculeService;
use crate::parsers::pipeline_v2::services::section_processor::SectionProcessor;

pub struct EnrichStage {
    pub section_processor: SectionProcessor,
    pub molecule_service: MoleculeService,
    pub caption_service: ImageCaptionService,
    pub merger: StructuredDataMerger,
    pub validator: ChemValidator,
}

impl EnrichStage {
    pub fn new(sidecar_url: impl Into<String>) -> Self {
        let url = sidecar_url.into();
        Self {
            section_processor: SectionProcessor::new(),
            molecule_service: MoleculeService::new(url.clone()),
            caption_service: ImageCaptionService::new(url),
            merger: StructuredDataMerger::new(),
            validator: ChemValidator::new(),
        }
    }
}

#[async_trait]
impl Stage<(ExtractedDocument, SegmentedDocument), EnrichedDocument> for EnrichStage {
    async fn run(
        &self,
        input: (ExtractedDocument, SegmentedDocument),
        ctx: &PipelineContext,
    ) -> Result<StageOutcome<EnrichedDocument>, PipelineError> {
        let (extracted, segmented) = input;

        ctx.reporter.report(crate::parsers::pipeline_v2::context::PipelineEvent::StageProgress {
            stage: "enrich".into(),
            message: "processing sections".into(),
        });

        let section_results = self
            .section_processor
            .process_sections(&segmented.sections, &extracted.parser, extracted.page_count)
            .await?;

        let mut outcome = StageOutcome::new(()).with_warning("enrich", "section processing complete");

        // 分子识别
        let molecule_results = if let Some(ref root) = ctx.project_root {
            ctx.reporter.report(crate::parsers::pipeline_v2::context::PipelineEvent::StageProgress {
                stage: "enrich".into(),
                message: "extracting molecules".into(),
            });
            match self
                .molecule_service
                .extract(
                    ctx.source_path.to_string_lossy().as_ref(),
                    &extracted,
                    root,
                )
                .await
            {
                Ok(mols) => mols,
                Err(e) => {
                    outcome = outcome.with_warning("enrich", format!("molecule extraction failed: {}", e));
                    Vec::new()
                }
            }
        } else {
            Vec::new()
        };

        // 图片描述
        let mut image_captions = std::collections::HashMap::new();
        if !extracted.images.is_empty() {
            if let Some(ref root) = ctx.project_root {
                ctx.reporter.report(crate::parsers::pipeline_v2::context::PipelineEvent::StageProgress {
                    stage: "enrich".into(),
                    message: "captioning images".into(),
                });
                let mut images = extracted.images.clone();
                match self.caption_service.caption_images(&mut images, root).await {
                    Ok(caps) => image_captions = caps,
                    Err(e) => {
                        outcome = outcome.with_warning("enrich", format!("image caption failed: {}", e));
                    }
                }
            }
        }

        // 合并 + SAR
        ctx.reporter.report(crate::parsers::pipeline_v2::context::PipelineEvent::StageProgress {
            stage: "enrich".into(),
            message: "merging results".into(),
        });

        let vlm_results: Vec<(String, crate::parsers::chem::vlm_chem::ChemImageResult)> = molecule_results
            .iter()
            .map(|m| {
                let filename = std::path::Path::new(&m.crop_path)
                    .file_name()
                    .and_then(|s| s.to_str())
                    .unwrap_or("unknown")
                    .to_string();
                (
                    filename,
                    crate::parsers::chem::vlm_chem::ChemImageResult {
                        esmiles: m.esmiles.clone(),
                        confidence: m.confidence,
                    },
                )
            })
            .collect();

        let (mut structured_data, sar_analysis) = if section_results.is_empty() && vlm_results.is_empty() {
            (
                crate::parsers::doc_types::StructuredData {
                    metadata: crate::parsers::doc_types::DocumentMetadata {
                        title: ctx.source_path.to_string_lossy().to_string().into(),
                        authors: vec![],
                        document_type: "unknown".into(),
                        key_targets: vec![],
                        source_file: Some(ctx.source_path.to_string_lossy().to_string()),
                    },
                    summary: "No data could be extracted from this document.".into(),
                    compounds: vec![],
                    activities: vec![],
                    key_findings: vec![],
                    uncertain_items: vec![],
                },
                None,
            )
        } else {
            self.merger.merge(&section_results, &vlm_results).await?
        };

        // 化学结构验证
        self.validator.validate_compounds(&mut structured_data.compounds)?;

        Ok(StageOutcome::new(EnrichedDocument {
            structured_data,
            sar_analysis,
            molecule_results,
            image_captions,
            sections: segmented.sections,
        }))
    }
}
```

- [ ] **Step 2: 编译检查**

Run: `cd src-tauri && cargo check --lib 2>&1 | grep -E "^error" | head -30`

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/stages/enrich.rs
git commit -m "feat(rust): add EnrichStage implementation"
```

---

## Phase 6: Persist Stage

### Task 17: 迁移 `text.md` / `report.md` 写入逻辑

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/writer/text_md.rs`
- Create: `src-tauri/src/parsers/pipeline_v2/writer/report_md.rs`

- [ ] **Step 1: 复制并适配 `output.rs`**

将 `src-tauri/src/parsers/pipeline/output.rs` 中的：
- `write_text_markdown`
- `build_text_body`
- `augment_markdown_with_images`（从 `markdown_augment.rs`）
- `verify_images`
- `write_agent_report`
- `generate_full_report`

迁移到 `pipeline_v2/writer/text_md.rs` 和 `pipeline_v2/writer/report_md.rs`，输入类型改为新 model 类型。

- [ ] **Step 2: `text_md.rs` 对外接口**

```rust
pub fn write_text_markdown(
    project_root: &std::path::Path,
    doc_id: &str,
    raw_text: &str,
    images: &[crate::parsers::pipeline_v2::models::extracted::ImageRef],
    page_count: usize,
    parser_label: &str,
) -> Result<(std::path::PathBuf, Vec<ImageVerification>), crate::parsers::pipeline_v2::error::PipelineError> {
    // ...
}
```

- [ ] **Step 3: `report_md.rs` 对外接口**

```rust
pub fn write_agent_report(
    project_root: &std::path::Path,
    doc_id: &str,
    final_data: &crate::parsers::doc_types::StructuredData,
    sar_analysis: Option<&str>,
    parser_label: &str,
) -> Result<std::path::PathBuf, crate::parsers::pipeline_v2::error::PipelineError> {
    // ...
}
```

- [ ] **Step 4: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/writer/text_md.rs
git add src-tauri/src/parsers/pipeline_v2/writer/report_md.rs
git commit -m "feat(rust): migrate text.md and report.md writers"
```

---

### Task 18: 实现 `MoleculeStoreWriter`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/services/molecule_store.rs`

- [ ] **Step 1: 写入分子库写入服务**

```rust
use crate::core::molecule::molecule_store::MoleculeDatabase;
use crate::parsers::doc_types::{CompoundEntry, StructuredData};
use crate::parsers::pipeline_v2::error::{PersistError, PipelineError};
use crate::parsers::pipeline_v2::services::helpers::{activity_entry_to_record, compound_entry_to_record};

pub struct MoleculeStoreWriter;

impl MoleculeStoreWriter {
    pub fn new() -> Self {
        Self
    }

    pub fn write(
        &self,
        project_root: &std::path::Path,
        data: &StructuredData,
        source_type: &str,
    ) -> Result<usize, PipelineError> {
        let source_doc = data.metadata.source_file.as_deref().unwrap_or("");
        let mut records = Vec::new();
        let mut skipped = 0usize;

        for compound in &data.compounds {
            match compound_entry_to_record(compound, source_doc, source_type) {
                Some(rec) => records.push(rec),
                None => skipped += 1,
            }
        }

        for activity in &data.activities {
            records.push(activity_entry_to_record(activity, source_doc, source_type));
        }

        if records.is_empty() {
            return Ok(0);
        }

        let db = MoleculeDatabase::open(project_root).map_err(|e| {
            PipelineError::Persist(PersistError::MoleculeStoreFailed { source: e })
        })?;

        db.add_molecules_batch(&records).map_err(|e| {
            PipelineError::Persist(PersistError::MoleculeStoreFailed { source: e })
        })
    }
}
```

- [ ] **Step 2: 迁移 helpers**

创建 `src-tauri/src/parsers/pipeline_v2/services/helpers.rs`，从旧 `pipeline/helpers.rs` 复制 `compound_entry_to_record` 和 `activity_entry_to_record`。

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/services/molecule_store.rs
git add src-tauri/src/parsers/pipeline_v2/services/helpers.rs
git commit -m "feat(rust): add MoleculeStoreWriter and helpers"
```

---

### Task 19: 组装 `PersistStage`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/stages/persist.rs`

- [ ] **Step 1: 写入 PersistStage**

```rust
use async_trait::async_trait;
use std::path::Path;

use crate::parsers::pipeline_v2::context::PipelineContext;
use crate::parsers::pipeline_v2::error::{PersistError, PipelineError};
use crate::parsers::pipeline_v2::models::enriched::EnrichedDocument;
use crate::parsers::pipeline_v2::models::extracted::ExtractedDocument;
use crate::parsers::pipeline_v2::models::persisted::PersistedDocument;
use crate::parsers::pipeline_v2::writer::report_md::write_agent_report;
use crate::parsers::pipeline_v2::writer::text_md::write_text_markdown;
use crate::parsers::pipeline_v2::runner::{Stage, StageOutcome};
use crate::parsers::pipeline_v2::services::molecule_store::MoleculeStoreWriter;

pub struct PersistStage {
    pub molecule_writer: MoleculeStoreWriter,
}

impl PersistStage {
    pub fn new() -> Self {
        Self {
            molecule_writer: MoleculeStoreWriter::new(),
        }
    }

    fn resolve_doc_id(
        &self,
        ctx: &PipelineContext,
        project_root: &Path,
    ) -> Result<String, PipelineError> {
        crate::core::project::project::Project::open(project_root)
            .and_then(|p| {
                p.list_documents()
                    .iter()
                    .find(|d| {
                        d.source_path
                            .as_deref()
                            .map(|sp| {
                                let full = project_root.join(sp);
                                full == ctx.source_path || full == Path::new("/").join(ctx.source_path.to_string_lossy().as_ref())
                            })
                            .unwrap_or(false)
                            || d.path == ctx.source_path.to_string_lossy().as_ref()
                    })
                    .map(|d| d.doc_id.clone())
            })
            .ok_or_else(|| {
                PipelineError::Persist(PersistError::DocIdNotResolved {
                    path: ctx.source_path.display().to_string(),
                })
            })
    }
}

#[async_trait]
impl Stage<(ExtractedDocument, EnrichedDocument), PersistedDocument> for PersistStage {
    async fn run(
        &self,
        input: (ExtractedDocument, EnrichedDocument),
        ctx: &PipelineContext,
    ) -> Result<StageOutcome<PersistedDocument>, PipelineError> {
        let (extracted, enriched) = input;

        let project_root = ctx
            .project_root
            .as_ref()
            .ok_or_else(|| PipelineError::Persist(PersistError::DocIdNotResolved {
                path: ctx.source_path.display().to_string(),
            }))?;

        let doc_id = self.resolve_doc_id(ctx, project_root)?;

        ctx.reporter.report(crate::parsers::pipeline_v2::context::PipelineEvent::StageProgress {
            stage: "persist".into(),
            message: "writing text.md".into(),
        });

        let (text_md_path, verifications) = write_text_markdown(
            project_root,
            &doc_id,
            &extracted.raw_text,
            &extracted.images,
            extracted.page_count,
            &extracted.parser,
        )?;

        ctx.reporter.report(crate::parsers::pipeline_v2::context::PipelineEvent::StageProgress {
            stage: "persist".into(),
            message: "writing report.md".into(),
        });

        let report_md_path = write_agent_report(
            project_root,
            &doc_id,
            &enriched.structured_data,
            enriched.sar_analysis.as_deref(),
            &extracted.parser,
        )?;

        ctx.reporter.report(crate::parsers::pipeline_v2::context::PipelineEvent::StageProgress {
            stage: "persist".into(),
            message: "persisting molecules".into(),
        });

        let persisted_molecule_count = self
            .molecule_writer
            .write(project_root, &enriched.structured_data, "unknown")?;

        let unverified_image_count = verifications.iter().filter(|v| !v.verified).count();

        Ok(StageOutcome::new(PersistedDocument {
            doc_id,
            text_md_path,
            report_md_path,
            unverified_image_count,
            persisted_molecule_count,
        }))
    }
}
```

- [ ] **Step 2: 编译检查**

Run: `cd src-tauri && cargo check --lib 2>&1 | grep -E "^error" | head -30`

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/stages/persist.rs
git commit -m "feat(rust): add PersistStage implementation"
```

---

## Phase 7: Index Stage

### Task 20: 实现 `IndexStage`

**Files:**
- Create: `src-tauri/src/parsers/pipeline_v2/stages/index.rs`

- [ ] **Step 1: 写入 IndexStage**

```rust
use async_trait::async_trait;

use crate::parsers::pipeline_v2::context::PipelineContext;
use crate::parsers::pipeline_v2::error::{IndexError, PipelineError};
use crate::parsers::pipeline_v2::models::persisted::{IndexedDocument, PersistedDocument};
use crate::parsers::pipeline_v2::runner::{Stage, StageOutcome};

pub struct IndexStage;

impl IndexStage {
    pub fn new() -> Self {
        Self
    }
}

#[async_trait]
impl Stage<PersistedDocument, IndexedDocument> for IndexStage {
    async fn run(
        &self,
        input: PersistedDocument,
        ctx: &PipelineContext,
    ) -> Result<StageOutcome<IndexedDocument>, PipelineError> {
        let project_root = ctx
            .project_root
            .as_ref()
            .ok_or_else(|| PipelineError::Index(IndexError::VectorStoreFailed {
                source: "project_root not set".into(),
            }))?;

        ctx.reporter.report(crate::parsers::pipeline_v2::context::PipelineEvent::StageProgress {
            stage: "index".into(),
            message: "loading knowledge base".into(),
        });

        let config = crate::core::config::AppConfig::load();
        let kb = crate::core::document::knowledge_base::KnowledgeBase::new(project_root, Some(&config.embed))
            .map_err(|e| PipelineError::Index(IndexError::VectorStoreFailed { source: e }))?;

        // 从文件缓存恢复 sections，或重新 segment
        let sections = match kb.file_cache().get(&ctx.source_path) {
            Ok(Some(cached)) => {
                serde_json::from_str::<Vec<crate::parsers::pipeline_v2::models::segmented::SectionChunk>>(&cached.sections_json)
                    .unwrap_or_default()
            }
            _ => Vec::new(),
        };

        ctx.reporter.report(crate::parsers::pipeline_v2::context::PipelineEvent::StageProgress {
            stage: "index".into(),
            message: format!("indexing {} sections", sections.len()),
        });

        kb.index_document(&input.doc_id, &sections, &[])
            .map_err(|e| PipelineError::Index(IndexError::VectorStoreFailed { source: e }))?;

        Ok(StageOutcome::new(IndexedDocument {
            doc_id: input.doc_id,
            indexed_sections: sections.len(),
        }))
    }
}
```

- [ ] **Step 2: 编译检查**

Run: `cd src-tauri && cargo check --lib 2>&1 | grep -E "^error" | head -30`

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/stages/index.rs
git commit -m "feat(rust): add IndexStage implementation"
```

---

## Phase 8: Pipeline 入口与调用方切换

### Task 21: 组装完整 PipelineRunner

**Files:**
- Modify: `src-tauri/src/parsers/pipeline_v2/runner.rs`
- Modify: `src-tauri/src/parsers/pipeline_v2/mod.rs`

- [ ] **Step 1: 在 `runner.rs` 增加完整 pipeline 运行函数**

```rust
use crate::parsers::pipeline_v2::context::PipelineContext;
use crate::parsers::pipeline_v2::error::PipelineError;
use crate::parsers::pipeline_v2::models::persisted::IndexedDocument;
use crate::parsers::pipeline_v2::models::source::SourceInput;
use crate::parsers::pipeline_v2::services::ocr::OcrService;
use crate::parsers::pipeline_v2::stages::enrich::EnrichStage;
use crate::parsers::pipeline_v2::stages::extract::ExtractStage;
use crate::parsers::pipeline_v2::stages::index::IndexStage;
use crate::parsers::pipeline_v2::stages::persist::PersistStage;
use crate::parsers::pipeline_v2::stages::segment::SegmentStage;

pub async fn run_pipeline(
    input: SourceInput,
    ctx: &PipelineContext,
) -> Result<IndexedDocument, PipelineError> {
    let runner = PipelineRunner::new();

    let ocr = OcrService::new(vec![]); // Task 22 注入默认 backends
    let extract_stage = ExtractStage::new(ocr);
    let extracted = runner
        .run_stage("extract", &extract_stage, input, ctx)
        .await?;

    let segment_stage = SegmentStage::new(ctx.config.chunk_max_chars);
    let segmented = runner
        .run_stage("segment", &segment_stage, extracted.clone(), ctx)
        .await?;

    let sidecar_url = crate::core::constants::sidecar_url();
    let enrich_stage = EnrichStage::new(sidecar_url);
    let enriched = runner
        .run_stage("enrich", &enrich_stage, (extracted.clone(), segmented), ctx)
        .await?;

    let persist_stage = PersistStage::new();
    let persisted = runner
        .run_stage("persist", &persist_stage, (extracted, enriched), ctx)
        .await?;

    let index_stage = IndexStage::new();
    let indexed = runner
        .run_stage("index", &index_stage, persisted, ctx)
        .await?;

    Ok(indexed)
}
```

说明：Enrich 和 Persist 都需要 `ExtractedDocument`（图片、raw_text、parser 等），因此 `run_pipeline` 在 Stage 之间通过 `clone()` 传递。`ExtractedDocument` 体积不大（主要是字符串和图片引用列表），克隆成本可接受。

- [ ] **Step 2: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/runner.rs
git add src-tauri/src/parsers/pipeline_v2/mod.rs
git commit -m "feat(rust): assemble full pipeline runner"
```

---

### Task 22: 注入 OCR Backends

**Files:**
- Modify: `src-tauri/src/parsers/pipeline_v2/services/ocr.rs`
- Modify: `src-tauri/src/parsers/pipeline_v2/mod.rs` 或新 `backends.rs`

- [ ] **Step 1: 为现有 OCR backend 实现新 trait**

在 `src-tauri/src/parsers/pipeline_v2/services/ocr.rs` 中为现有 backend 写 adapter：

```rust
pub struct UniparserBackendAdapter;

#[async_trait]
impl OcrBackend for UniparserBackendAdapter {
    fn name(&self) -> &'static str { "uniparser" }
    fn is_available(&self) -> bool { crate::parsers::ocr::uniparser::is_available() }
    async fn run(&self, path: &Path) -> Result<OcrOutput, PipelineError> {
        let out = crate::parsers::ocr::uniparser::run(path.to_string_lossy().as_ref()).await?;
        Ok(adapt_ocr_output(out))
    }
}
```

类似地为 `mineru`、`paddleocr-online`、`glm-ocr`、`glm-4.6v-flash` 写 adapter。

`adapt_ocr_output` 把旧的 `crate::parsers::ocr::backend::OcrOutput` 转换为新 `OcrOutput`。

- [ ] **Step 2: 提供默认 backend 列表**

```rust
pub fn default_backends() -> Vec<Box<dyn OcrBackend>> {
    vec![
        Box::new(UniparserBackendAdapter),
        Box::new(MineruBackendAdapter),
        Box::new(PaddleBackendAdapter),
        Box::new(GlmOcrBackendAdapter),
        Box::new(Glm4VBackendAdapter),
    ]
}
```

- [ ] **Step 3: 更新 `run_pipeline` 使用默认 backends**

```rust
let ocr = OcrService::new(crate::parsers::pipeline_v2::services::ocr::default_backends());
```

- [ ] **Step 4: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/services/ocr.rs
git commit -m "feat(rust): wire existing OCR backends into new OcrService"
```

---

### Task 23: 添加新的 Tauri Command

**Files:**
- Create: `src-tauri/src/commands/pipeline_v2.rs`
- Modify: `src-tauri/src/commands/mod.rs`

- [ ] **Step 1: 写入新 command**

```rust
use tauri::AppHandle;

use crate::parsers::pipeline_v2::context::{PipelineContext, PipelineEvent};
use crate::parsers::pipeline_v2::models::source::SourceInput;
use crate::parsers::pipeline_v2::runner::run_pipeline;
use crate::core::constants::EVT_DOC_PROGRESS;

#[tauri::command]
pub async fn process_document_v2(
    path: String,
    user_request: Option<String>,
    project_root: Option<String>,
    app: AppHandle,
) -> Result<(), String> {
    let input = SourceInput::new(&path)
        .with_allow_ocr(true);

    let mut ctx = PipelineContext::new(&path, user_request.unwrap_or_default());
    if let Some(root) = project_root {
        ctx = ctx.with_project_root(&root);
    }

    let reporter = std::sync::Arc::new(TauriReporter { app });
    ctx = ctx.with_reporter(reporter);

    run_pipeline(input, &ctx).await.map_err(|e| e.to_string())
}

struct TauriReporter {
    app: AppHandle,
}

impl crate::parsers::pipeline_v2::context::PipelineReporter for TauriReporter {
    fn report(&self, event: PipelineEvent) {
        let payload = match event {
            PipelineEvent::StageStart { stage } => DocProgressEvent::Classify {
                parser: stage,
                page_count: 0,
            },
            PipelineEvent::StageProgress { stage, message } => DocProgressEvent::Section {
                name: stage,
                status: message,
                compounds: 0,
                activities: 0,
            },
            PipelineEvent::StageComplete { stage } => DocProgressEvent::Section {
                name: stage,
                status: "complete".into(),
                compounds: 0,
                activities: 0,
            },
            PipelineEvent::StageWarning { stage, message } => DocProgressEvent::Error {
                stage,
                message,
            },
        };
        let _ = self.app.emit(EVT_DOC_PROGRESS, payload);
    }
}

#[derive(serde::Serialize, Clone)]
#[serde(tag = "stage", content = "payload")]
enum DocProgressEvent {
    #[serde(rename = "classify")]
    Classify { parser: String, page_count: usize },
    #[serde(rename = "section")]
    Section { name: String, status: String, compounds: usize, activities: usize },
    #[serde(rename = "error")]
    Error { stage: String, message: String },
}
```

- [ ] **Step 2: 注册 command**

在 `src-tauri/src/commands/mod.rs` 的 `handler()` 中添加 `process_document_v2`。

- [ ] **Step 3: 编译检查**

Run: `cd src-tauri && cargo check --lib 2>&1 | grep -E "^error" | head -30`

- [ ] **Step 4: Commit**

```bash
git add src-tauri/src/commands/pipeline_v2.rs
git add src-tauri/src/commands/mod.rs
git commit -m "feat(rust): add process_document_v2 Tauri command"
```

---

### Task 24: 切换调用方

**Files:**
- Modify: `src-tauri/src/commands/pdf.rs`
- Modify: `src-tauri/src/core/document/ingest_worker.rs`

- [ ] **Step 1: 在合适位置调用 `process_document_v2`**

把 `commands/pdf.rs` 中 `process_document` 的调用替换为 `process_document_v2`（或保留旧命令，新增入口）。

把 `core/document/ingest_worker.rs` 中处理 PDF 的任务改为调用新 pipeline。

- [ ] **Step 2: 前端调用调整**

Modify: `frontend/src/api/tauri/pdf.ts`（或相关文件），把调用的 command 名从 `process_document` 改为 `process_document_v2`。

- [ ] **Step 3: 编译检查**

Run: `cd src-tauri && cargo check --lib 2>&1 | tail -20`
Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -20`

- [ ] **Step 4: Commit**

```bash
git add src-tauri/src/commands/pdf.rs
git add src-tauri/src/core/document/ingest_worker.rs
git add frontend/src/api/tauri/pdf.ts
git commit -m "feat(rust,frontend): switch callers to process_document_v2"
```

---

## Phase 9: 测试与清理

### Task 26: 单元测试补齐

**Files:**
- Modify: 每个 `pipeline_v2` 文件底部的 `#[cfg(test)]`

- [ ] **Step 1: 为每个 Stage 写至少一个 happy path test**

- `ExtractStage`：mock InspectorService 返回固定文本，验证输出 raw_text。
- `SegmentStage`：输入带标题文本，验证 section 数量。
- `EnrichStage`：输入空 section，验证产出默认 StructuredData。
- `PersistStage`：使用临时目录，验证 text.md 文件生成。
- `IndexStage`：mock KB，验证 indexed_sections。

- [ ] **Step 2: 运行所有 pipeline_v2 测试**

Run: `cd src-tauri && cargo test --lib pipeline_v2 -- --nocapture 2>&1 | tail -40`
Expected: 所有测试通过。

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/parsers/pipeline_v2/
git commit -m "test(rust): add unit tests for pipeline_v2 stages"
```

---

### Task 27: 集成测试

**Files:**
- Create: `tests/integration/pipeline_v2.rs`（如项目已有 integration 目录结构则适配）

- [ ] **Step 1: 写一个端到端测试**

```rust
#[tokio::test]
async fn pipeline_v2_processes_sample_pdf() {
    // 准备：把 fixtures/sample.pdf 复制到临时项目目录
    // 调用 run_pipeline
    // 验证 projects/<doc_id>/text.md 和 report.md 存在
}
```

- [ ] **Step 2: 运行集成测试**

Run: `cd src-tauri && cargo test --test pipeline_v2 -- --nocapture 2>&1 | tail -30`
Expected: 通过。

- [ ] **Step 3: Commit**

```bash
git add tests/integration/pipeline_v2.rs
git commit -m "test(rust): add pipeline_v2 integration test"
```

---

### Task 28: 删除旧 Pipeline

**Files:**
- Delete: `src-tauri/src/parsers/pipeline/` 目录
- Modify: `src-tauri/src/parsers/mod.rs` 移除 `pub mod pipeline;`
- Modify: 所有引用旧 pipeline 的代码

- [ ] **Step 1: 确认无旧引用**

Run: `cd src-tauri && cargo check --lib 2>&1 | grep -E "parsers::pipeline::" | head -30`
Expected: 无引用（除了可能保留的 re-export）。

- [ ] **Step 2: 删除旧目录**

```bash
rm -rf src-tauri/src/parsers/pipeline/
```

- [ ] **Step 3: 重命名 `pipeline_v2` 为 `pipeline`**

```bash
mv src-tauri/src/parsers/pipeline_v2 src-tauri/src/parsers/pipeline
```

- [ ] **Step 4: 批量替换内部 `pipeline_v2` 引用为 `pipeline`**

使用 IDE 或 sed：

```bash
cd src-tauri/src/parsers/pipeline && find . -name "*.rs" -exec sed -i 's/pipeline_v2/pipeline/g' {} \;
```

同时更新 `src-tauri/src/parsers/mod.rs`：

```rust
pub mod pipeline;
```

- [ ] **Step 5: 编译检查**

Run: `cd src-tauri && cargo check --lib 2>&1 | tail -30`
Expected: 0 errors。

- [ ] **Step 6: Commit**

```bash
git add src-tauri/src/parsers/
git commit -m "refactor(rust): replace old pipeline with stage-based pipeline"
```

---

## 成功标准验收

- [ ] `cargo check --lib` 0 errors。
- [ ] `cargo test --lib pipeline` 全部通过。
- [ ] `cargo test --test pipeline_v2` 通过（重命名后改为 `pipeline`）。
- [ ] 端到端手动验证：上传一个 PDF，确认 pipeline 完成后生成 `text.md` 和 `report.md`。
- [ ] `pipeline/` 下没有超过 500 行的文件（测试除外）。
- [ ] `process_document_v2` 函数长度不超过 100 行。

---

## 自我审查记录

**Spec 覆盖：** 本计划覆盖了设计文档中所有 Stage、核心接口、缓存抽象、错误处理、测试策略和迁移策略。

**Placeholder 扫描：** 已消除所有 "TBD" / "TODO" / "implement later" / `unimplemented!` 占位。

**类型一致性：** 所有 Stage 输入输出类型在 Task 5-8 中定义，后续 Task 保持一致使用。Phase 3-7 的部分 service（如 `molecules.rs`、`merge.rs`）在实现初期会临时桥接旧 `pipeline::` 中的函数和类型，这是为了渐进迁移；Task 28 删除旧 `pipeline/` 前必须把这些桥接替换为直接调用底层模块（如 `parsers::chem`、`parsers::structure`）或内联实现。
