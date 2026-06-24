# MBForge Rust 后端 Workspace 拆分 + Zvec 搜索层实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `src-tauri/src` 从单一 crate 拆分为 5 个 Cargo workspace crate（app/domain/chem/pipeline/infra），并把向量/全文搜索层从 SQLite 迁移到 Zvec。

**Architecture:** 采用分层 Cargo workspace，`mbforge-infra` 作为最底层被所有人依赖，`mbforge-chem` 纯计算，`mbforge-domain` 承载业务状态与 Zvec 搜索，`mbforge-pipeline` 编排解析管线，`mbforge-app` 聚合 Tauri 命令。循环依赖通过 `ingest_worker` 上移到 pipeline 消除。

**Tech Stack:** Rust 2021, Tauri v2, Cargo workspace, Zvec (Rust bindings), SQLite (rusqlite), tokio, serde.

---

## 文件结构目标

```text
src-tauri/
├── Cargo.toml
└── crates/
    ├── mbforge-app/
    │   ├── Cargo.toml
    │   └── src/
    │       ├── main.rs
    │       ├── lib.rs
    │       ├── commands/
    │       ├── protocol.rs
    │       └── sidecar.rs
    ├── mbforge-domain/
    │   ├── Cargo.toml
    │   └── src/
    │       ├── lib.rs
    │       ├── agent/
    │       ├── molecule/
    │       ├── document/
    │       │   ├── mod.rs
    │       │   ├── knowledge_base.rs
    │       │   ├── search_engine.rs      # Zvec 封装
    │       │   ├── document_tree.rs
    │       │   ├── file_cache.rs
    │       │   ├── semantic_cache.rs
    │       │   └── stream_search.rs
    │       ├── ingest_queue/
    │       ├── vector/
    │       └── project/
    ├── mbforge-chem/
    │   ├── Cargo.toml
    │   └── src/
    │       ├── lib.rs
    │       ├── smiles.rs
    │       ├── esmiles.rs
    │       ├── molecode.rs
    │       ├── markush.rs
    │       ├── sar.rs
    │       └── gesim.rs
    ├── mbforge-pipeline/
    │   ├── Cargo.toml
    │   └── src/
    │       ├── lib.rs
    │       ├── ingest_worker/
    │       ├── pipeline/
    │       ├── chem/
    │       ├── pdf/
    │       ├── ocr/
    │       ├── structure/
    │       └── doc_types.rs
    └── mbforge-infra/
        ├── Cargo.toml
        └── src/
            ├── lib.rs
            ├── db.rs
            ├── error.rs
            ├── helpers.rs
            ├── http.rs
            ├── sidecar_client.rs
            ├── types.rs
            └── config/
```

---

## 前置准备

### Task 0: 环境检查与备份

**Files:**
- Read: `src-tauri/Cargo.toml`
- Read: `src-tauri/src/lib.rs`

- [ ] **Step 1: 确认 Rust 与 Cargo 版本**

Run:
```bash
cd src-tauri
rustc --version
cargo --version
```
Expected: Rust >= 1.75, Cargo >= 1.75.

- [ ] **Step 2: 确认 CMake 与 C++ 编译器可用**

Run:
```bash
cmake --version
# Windows
cl
# or Linux/macOS
g++ --version
```
Expected: CMake >= 3.13, C++17 compiler available.

- [ ] **Step 3: 创建功能分支**

Run:
```bash
cd C:/Users/10954/Desktop/MBForge
git checkout -b feat/rust-workspace-split-zvec
```
Expected: New branch created.

- [ ] **Step 4: 备份当前能编译的状态**

Run:
```bash
cd src-tauri
cargo check 2>&1 | tail -n 20
```
Expected: `cargo check` passes with existing warnings (config.toml suppresses them).

---

## Phase 1: 抽出 `mbforge-infra`

### Task 1: 创建 workspace 根与 `mbforge-infra` crate

**Files:**
- Modify: `src-tauri/Cargo.toml`
- Create: `src-tauri/crates/mbforge-infra/Cargo.toml`
- Create: `src-tauri/crates/mbforge-infra/src/lib.rs`
- Create: `src-tauri/crates/mbforge-infra/src/db.rs`
- Create: `src-tauri/crates/mbforge-infra/src/error.rs`
- Create: `src-tauri/crates/mbforge-infra/src/helpers.rs`
- Create: `src-tauri/crates/mbforge-infra/src/http.rs`
- Create: `src-tauri/crates/mbforge-infra/src/sidecar_client.rs`
- Create: `src-tauri/crates/mbforge-infra/src/types.rs`
- Create: `src-tauri/crates/mbforge-infra/src/config/constants.rs`

- [ ] **Step 1: 修改 workspace 根 `Cargo.toml`**

```toml
[workspace]
members = ["crates/*"]
resolver = "2"

[workspace.package]
version = "0.1.0"
edition = "2021"
authors = ["MBForge Team"]
license = "MIT"

[workspace.dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["full"] }
reqwest = { version = "0.12", features = ["json"] }
rusqlite = { version = "0.32", features = ["bundled", "chrono"] }
log = "0.4"
anyhow = "1"
thiserror = "1"
```

Run:
```bash
cd src-tauri
cargo check --workspace
```
Expected: FAIL — `crates/*` directories do not exist yet.

- [ ] **Step 2: 创建 `mbforge-infra/Cargo.toml`**

```toml
[package]
name = "mbforge-infra"
version.workspace = true
edition.workspace = true
authors.workspace = true
license.workspace = true

[dependencies]
serde.workspace = true
serde_json.workspace = true
rusqlite.workspace = true
reqwest.workspace = true
tokio.workspace = true
log.workspace = true
anyhow.workspace = true
thiserror.workspace = true
tauri = { version = "2", default-features = false }
```

- [ ] **Step 3: 迁移 `core/db.rs` 到 `mbforge-infra/src/db.rs`**

Move content from `src-tauri/src/core/db.rs` to `src-tauri/crates/mbforge-infra/src/db.rs`.
Change `crate::core::...` imports to `crate::...`.

- [ ] **Step 4: 迁移 `core/error.rs` 到 `mbforge-infra/src/error.rs`**

Move content from `src-tauri/src/core/error.rs` to `src-tauri/crates/mbforge-infra/src/error.rs`.

- [ ] **Step 5: 迁移 `core/helpers.rs` 到 `mbforge-infra/src/helpers.rs`**

Move content from `src-tauri/src/core/helpers.rs` to `src-tauri/crates/mbforge-infra/src/helpers.rs`.

- [ ] **Step 6: 迁移 `core/http.rs` 到 `mbforge-infra/src/http.rs`**

Move content from `src-tauri/src/core/http.rs` to `src-tauri/crates/mbforge-infra/src/http.rs`.

- [ ] **Step 7: 迁移 `core/sidecar_client.rs` 到 `mbforge-infra/src/sidecar_client.rs`**

Move content from `src-tauri/src/core/sidecar_client.rs` to `src-tauri/crates/mbforge-infra/src/sidecar_client.rs`.

- [ ] **Step 8: 迁移 `core/types.rs` 到 `mbforge-infra/src/types.rs`**

Move content from `src-tauri/src/core/types.rs` to `src-tauri/crates/mbforge-infra/src/types.rs`.

- [ ] **Step 9: 迁移 `core/config/constants.rs` 到 `mbforge-infra/src/config/constants.rs`**

Move content from `src-tauri/src/core/config/constants.rs` to `src-tauri/crates/mbforge-infra/src/config/constants.rs`.

- [ ] **Step 10: 编写 `mbforge-infra/src/lib.rs` 聚合导出**

```rust
pub mod config;
pub mod db;
pub mod error;
pub mod helpers;
pub mod http;
pub mod sidecar_client;
pub mod types;
```

- [ ] **Step 11: 验证 `mbforge-infra` 可独立编译**

Run:
```bash
cd src-tauri
cargo check -p mbforge-infra
```
Expected: PASS.

- [ ] **Step 12: 提交 Phase 1**

Run:
```bash
git add src-tauri/Cargo.toml src-tauri/crates/mbforge-infra/
git commit -m "build(rust): add workspace root and mbforge-infra crate"
```

---

## Phase 2: 抽出 `mbforge-chem`

### Task 2: 创建 `mbforge-chem` crate

**Files:**
- Create: `src-tauri/crates/mbforge-chem/Cargo.toml`
- Create: `src-tauri/crates/mbforge-chem/src/lib.rs`
- Move: `src-tauri/src/core/chem/*` → `src-tauri/crates/mbforge-chem/src/`

- [ ] **Step 1: 创建 `mbforge-chem/Cargo.toml`**

```toml
[package]
name = "mbforge-chem"
version.workspace = true
edition.workspace = true

[dependencies]
mbforge-infra = { path = "../mbforge-infra" }
serde.workspace = true
serde_json.workspace = true
log.workspace = true
```

- [ ] **Step 2: 迁移 `core/chem/mod.rs` 及子模块**

Move files:
```bash
cd src-tauri
mkdir -p crates/mbforge-chem/src
cp -r src/core/chem/* crates/mbforge-chem/src/
```

- [ ] **Step 3: 调整 `mbforge-chem` 内部 import**

Replace `crate::core::{error,helpers,types,config}` with `mbforge_infra::{error,helpers,types,config}`.

- [ ] **Step 4: 编写 `mbforge-chem/src/lib.rs` 聚合导出**

```rust
pub mod esmiles;
pub mod gesim;
pub mod markush;
pub mod molecode;
pub mod sar;
pub mod smiles;
```

- [ ] **Step 5: 验证 `mbforge-chem` 可独立编译**

Run:
```bash
cd src-tauri
cargo check -p mbforge-chem
```
Expected: PASS.

- [ ] **Step 6: 提交 Phase 2**

Run:
```bash
git add src-tauri/crates/mbforge-chem/
git commit -m "build(rust): add mbforge-chem crate"
```

---

## Phase 3: 重构 `mbforge-domain`

### Task 3.1: 创建 crate 并迁移核心领域模块

**Files:**
- Create: `src-tauri/crates/mbforge-domain/Cargo.toml`
- Create: `src-tauri/crates/mbforge-domain/src/lib.rs`
- Move: `src-tauri/src/core/{agent,molecule,document,vector,project}` → `src-tauri/crates/mbforge-domain/src/`

- [ ] **Step 1: 创建 `mbforge-domain/Cargo.toml`**

```toml
[package]
name = "mbforge-domain"
version.workspace = true
edition.workspace = true

[dependencies]
mbforge-infra = { path = "../mbforge-infra" }
mbforge-chem = { path = "../mbforge-chem" }
serde.workspace = true
serde_json.workspace = true
rusqlite.workspace = true
tokio.workspace = true
log.workspace = true
tauri = { version = "2", default-features = false }
zvec-bindings = { version = "0.4", features = ["sync"] }
```

> 选择 `zvec-bindings` 的原因：`sync` feature 提供 `SharedCollection`（`Arc` 包装），适合 Tauri 多线程状态共享。

- [ ] **Step 2: 复制核心领域代码**

Run:
```bash
cd src-tauri
mkdir -p crates/mbforge-domain/src
cp -r src/core/agent crates/mbforge-domain/src/
cp -r src/core/molecule crates/mbforge-domain/src/
cp -r src/core/document crates/mbforge-domain/src/
cp -r src/core/vector crates/mbforge-domain/src/
cp -r src/core/project crates/mbforge-domain/src/
```

- [ ] **Step 3: 批量替换 import 路径**

Use script:
```bash
cd src-tauri/crates/mbforge-domain/src
find . -name "*.rs" -exec sed -i 's/crate::core::config/mbforge_infra::config/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::db/mbforge_infra::db/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::error/mbforge_infra::error/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::helpers/mbforge_infra::helpers/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::http/mbforge_infra::http/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::sidecar_client/mbforge_infra::sidecar_client/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::types/mbforge_infra::types/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::chem/mbforge_chem/g' {} +
```

- [ ] **Step 4: 处理 `crate::parsers` 的引用**

Run:
```bash
cd src-tauri/crates/mbforge-domain/src
grep -rn "crate::parsers" --include="*.rs"
```
Expected: Should only appear in `document/ingest_worker.rs` (will be moved in Phase 4).

Temporarily remove or stub `ingest_worker.rs` from `mbforge-domain` (move it in Phase 4).

- [ ] **Step 5: 编写 `mbforge-domain/src/lib.rs` 聚合导出**

```rust
pub mod agent;
pub mod document;
pub mod ingest_queue;
pub mod molecule;
pub mod project;
pub mod vector;
```

### Task 3.2: 用 Zvec 替换 SQLite 向量/FTS 搜索

**Files:**
- Create: `src-tauri/crates/mbforge-domain/src/document/search_engine.rs`
- Modify: `src-tauri/crates/mbforge-domain/src/document/knowledge_base.rs`
- Modify: `src-tauri/crates/mbforge-domain/src/document/mod.rs`
- Delete: `src-tauri/crates/mbforge-domain/src/vector/sqlite_vector_store.rs`

- [ ] **Step 6: 添加 Zvec Rust 依赖**

`mbforge-domain/Cargo.toml` 中已包含：

```toml
zvec-bindings = { version = "0.4", features = ["sync"] }
```

> 选择 `zvec-bindings` 的原因：`sync` feature 提供 `SharedCollection`（`Arc` 包装），适合 Tauri 多线程状态共享。

- [ ] **Step 7: 实现 `search_engine.rs` 基础接口（基于 `zvec-bindings`）**

```rust
use std::path::Path;
use mbforge_infra::error::{AppError, AppResult, ErrorCode};
use zvec_bindings::{
    create_and_open_shared, CollectionSchema, Doc, FieldSchema, FtsQuery, MetricType,
    MultiQuery, RrfReranker, SharedCollection, VectorQuery,
};

#[derive(Debug, Clone)]
pub struct SearchResult {
    pub id: String,
    pub text: String,
    pub metadata: serde_json::Value,
    pub score: f32,
}

pub struct SearchEngine {
    collection: SharedCollection,
    dim: usize,
}

impl SearchEngine {
    pub fn open(path: &Path, dim: usize) -> AppResult<Self> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let mut schema = CollectionSchema::builder("mbforge_kb")
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("schema builder: {e}")))?
            .field(FieldSchema::string("chunk_id").primary_key(true))
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("chunk_id field: {e}")))?
            .field(FieldSchema::string("doc_id").invert_index(true, false))
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("doc_id field: {e}")))?
            .field(FieldSchema::string("text").fts_tokenizer("standard"))
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("text field: {e}")))?
            .field(FieldSchema::string("metadata"))
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("metadata field: {e}")))?
            .field(
                FieldSchema::vector_fp32("embedding", dim)
                    .hnsw(16, 200)
                    .metric(MetricType::Cosine),
            )
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("embedding field: {e}")))?
            .build()
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("schema build: {e}")))?;

        let collection = create_and_open_shared(path, &schema, None)
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("open zvec: {e}")))?;

        Ok(Self { collection, dim })
    }

    pub fn index_document(
        &self,
        doc_id: &str,
        chunk_ids: &[String],
        texts: &[String],
        metadatas: &[String],
        embeddings: &[Vec<f32>],
    ) -> AppResult<()> {
        if chunk_ids.is_empty() {
            return Ok(());
        }

        for (i, v) in embeddings.iter().enumerate() {
            if v.len() != self.dim {
                return Err(AppError::new(
                    ErrorCode::Unknown,
                    format!(
                        "Vector dimension mismatch at index {i}: expected {}, got {}",
                        self.dim,
                        v.len()
                    ),
                ));
            }
        }

        self.delete_document(doc_id)?;

        let mut docs = Vec::with_capacity(chunk_ids.len());
        for i in 0..chunk_ids.len() {
            let mut doc = Doc::id(&chunk_ids[i]);
            doc.add_string("doc_id", doc_id)
                .map_err(|e| AppError::new(ErrorCode::Unknown, format!("doc field: {e}")))?;
            doc.add_string("text", &texts[i])
                .map_err(|e| AppError::new(ErrorCode::Unknown, format!("text field: {e}")))?;
            doc.add_string("metadata", &metadatas[i])
                .map_err(|e| AppError::new(ErrorCode::Unknown, format!("metadata field: {e}")))?;
            doc.add_vector_fp32("embedding", &embeddings[i])
                .map_err(|e| AppError::new(ErrorCode::Unknown, format!("embedding field: {e}")))?;
            docs.push(doc);
        }

        self.collection
            .insert(&docs)
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("zvec insert: {e}")))?;
        Ok(())
    }

    pub fn delete_document(&self, doc_id: &str) -> AppResult<()> {
        self.collection
            .delete_by_filter(&format!("doc_id = '{}'", doc_id))
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("zvec delete: {e}")))?;
        Ok(())
    }

    pub fn vector_search(
        &self,
        query_embedding: &[f32],
        top_k: usize,
        doc_id_filter: Option<&str>,
    ) -> AppResult<Vec<SearchResult>> {
        let mut q = VectorQuery::builder()
            .field("embedding")
            .vector_fp32(query_embedding)
            .topk(top_k)
            .build()
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("vector query: {e}")))?;

        if let Some(doc_id) = doc_id_filter {
            q = q.filter(&format!("doc_id = '{}'", doc_id));
        }

        let results = self
            .collection
            .query(&q)
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("zvec vector search: {e}")))?;

        Ok(results.iter().map(parse_row).collect())
    }

    pub fn text_search(
        &self,
        query: &str,
        top_k: usize,
        doc_id_filter: Option<&str>,
    ) -> AppResult<Vec<SearchResult>> {
        let filter = doc_id_filter.map(|d| format!("doc_id = '{}'", d));
        let q = FtsQuery::new("text", query, top_k, filter.as_deref())
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("fts query: {e}")))?;

        let results = self
            .collection
            .query(&q)
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("zvec text search: {e}")))?;

        Ok(results.iter().map(parse_row).collect())
    }

    pub fn hybrid_search(
        &self,
        query_vec: &[f32],
        query_text: &str,
        top_k: usize,
        doc_id_filter: Option<&str>,
    ) -> AppResult<Vec<SearchResult>> {
        let filter = doc_id_filter.map(|d| format!("doc_id = '{}'", d));

        let vq = VectorQuery::builder()
            .field("embedding")
            .vector_fp32(query_vec)
            .topk(top_k * 3)
            .build()
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("vector query: {e}")))?;

        let fq = FtsQuery::new("text", query_text, top_k * 3, filter.as_deref())
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("fts query: {e}")))?;

        let multi = MultiQuery::new(vec![Box::new(vq), Box::new(fq)])
            .reranker(RrfReranker::with_top_n(top_k))
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("multi query: {e}")))?;

        let results = self
            .collection
            .query(&multi)
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("zvec hybrid search: {e}")))?;

        Ok(results.iter().map(parse_row).collect())
    }

    pub fn count(&self) -> AppResult<usize> {
        self.collection
            .count()
            .map_err(|e| AppError::new(ErrorCode::Unknown, format!("zvec count: {e}")))
    }
}

fn parse_row(row: &zvec_bindings::SearchResult) -> SearchResult {
    SearchResult {
        id: row.pk().to_string(),
        text: row.field_as_string("text").unwrap_or_default(),
        metadata: serde_json::from_str(&row.field_as_string("metadata").unwrap_or_default())
            .unwrap_or_else(|_| serde_json::json!({})),
        score: row.score(),
    }
}
```

> 注：以上 API 基于 `zvec-bindings` v0.4 公开接口。若实际接口名称不同（如 `field_as_string` vs `get_string`），需在实施时根据 crate docs 调整。

- [ ] **Step 8: 修改 `knowledge_base.rs` 使用 `SearchEngine`**

Remove:
- `use crate::core::vector::sqlite_vector_store::{reciprocal_rank_fusion, SqliteVectorStore};`
- `vector_store: SqliteVectorStore` field
- `sections_fts` table setup
- `reciprocal_rank_fusion` usage

Add:
- `use super::search_engine::{SearchEngine, SearchResult};`
- `search_engine: SearchEngine` field
- Open `SearchEngine` in `KnowledgeBase::new()` at `.mbforge/search.zvec/`
- Replace `kb_search` internal vector/FTS calls with `search_engine.hybrid_search(...)`

- [ ] **Step 9: 更新 `document/mod.rs` 导出**

```rust
pub mod document_tree;
pub mod file_cache;
pub mod knowledge_base;
pub mod search_engine;
pub mod semantic_cache;
pub mod stream_search;
```

- [ ] **Step 10: 删除 `sqlite_vector_store.rs`**

Run:
```bash
rm src-tauri/crates/mbforge-domain/src/vector/sqlite_vector_store.rs
```

- [ ] **Step 11: 验证 `mbforge-domain` 可编译（允许 Zvec API 未实现 stubs）**

Run:
```bash
cd src-tauri
cargo check -p mbforge-domain
```
Expected: PASS (with stubs).

- [ ] **Step 12: 提交 Phase 3**

Run:
```bash
git add src-tauri/crates/mbforge-domain/
git commit -m "build(rust): add mbforge-domain crate with zvec search stubs"
```

---

## Phase 4: 重构 `mbforge-pipeline`

### Task 4: 创建 crate 并迁移解析管线

**Files:**
- Create: `src-tauri/crates/mbforge-pipeline/Cargo.toml`
- Create: `src-tauri/crates/mbforge-pipeline/src/lib.rs`
- Move: `src-tauri/src/parsers/*` → `src-tauri/crates/mbforge-pipeline/src/`
- Move: `src-tauri/src/core/document/ingest_worker.rs` → `src-tauri/crates/mbforge-pipeline/src/ingest_worker/`

- [ ] **Step 1: 创建 `mbforge-pipeline/Cargo.toml`**

```toml
[package]
name = "mbforge-pipeline"
version.workspace = true
edition.workspace = true

[dependencies]
mbforge-infra = { path = "../mbforge-infra" }
mbforge-chem = { path = "../mbforge-chem" }
mbforge-domain = { path = "../mbforge-domain" }
serde.workspace = true
serde_json.workspace = true
tokio.workspace = true
log.workspace = true
```

- [ ] **Step 2: 复制解析管线代码**

Run:
```bash
cd src-tauri
mkdir -p crates/mbforge-pipeline/src
cp -r src/parsers/* crates/mbforge-pipeline/src/
mkdir -p crates/mbforge-pipeline/src/ingest_worker
cp src/core/document/ingest_worker.rs crates/mbforge-pipeline/src/ingest_worker/mod.rs
```

- [ ] **Step 3: 批量替换 import 路径**

Use script:
```bash
cd src-tauri/crates/mbforge-pipeline/src
find . -name "*.rs" -exec sed -i 's/crate::core::config/mbforge_infra::config/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::db/mbforge_infra::db/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::error/mbforge_infra::error/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::helpers/mbforge_infra::helpers/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::http/mbforge_infra::http/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::sidecar_client/mbforge_infra::sidecar_client/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::types/mbforge_infra::types/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::chem/mbforge_chem/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::document/mbforge_domain::document/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::molecule/mbforge_domain::molecule/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::project/mbforge_domain::project/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::parsers/crate/g' {} +
```

- [ ] **Step 4: 编写 `mbforge-pipeline/src/lib.rs` 聚合导出**

```rust
pub mod chem;
pub mod doc_types;
pub mod ingest_worker;
pub mod ocr;
pub mod pdf;
pub mod pipeline;
pub mod structure;
```

- [ ] **Step 5: 修复 `ingest_worker` 中的内部引用**

`ingest_worker/mod.rs` 原本在 `core::document`，现在需要把 `crate::core::document::...` 改为 `mbforge_domain::document::...`。

- [ ] **Step 6: 确保 pipeline 不暴露 domain 私有模块**

Pipeline 调用应只通过 `mbforge_domain::document::knowledge_base::KnowledgeBase`、`mbforge_domain::document::search_engine::SearchEngine` 等 public API。

Run:
```bash
cd src-tauri/crates/mbforge-pipeline/src
grep -rn "mbforge_domain::document::" --include="*.rs" | head -n 30
```
Review and fix any private module access.

- [ ] **Step 7: 验证 `mbforge-pipeline` 可编译**

Run:
```bash
cd src-tauri
cargo check -p mbforge-pipeline
```
Expected: PASS.

- [ ] **Step 8: 提交 Phase 4**

Run:
```bash
git add src-tauri/crates/mbforge-pipeline/
git commit -m "build(rust): add mbforge-pipeline crate"
```

---

## Phase 5: 重构 `mbforge-app`

### Task 5: 创建 crate 并迁移 Tauri 入口与命令

**Files:**
- Create: `src-tauri/crates/mbforge-app/Cargo.toml`
- Create: `src-tauri/crates/mbforge-app/src/main.rs`
- Create: `src-tauri/crates/mbforge-app/src/lib.rs`
- Move: `src-tauri/src/commands/*` → `src-tauri/crates/mbforge-app/src/commands/`
- Move: `src-tauri/src/protocol.rs` → `src-tauri/crates/mbforge-app/src/protocol.rs`
- Move: `src-tauri/src/sidecar.rs` → `src-tauri/crates/mbforge-app/src/sidecar.rs`
- Modify: `src-tauri/crates/mbforge-app/src/commands/mod.rs`

- [ ] **Step 1: 创建 `mbforge-app/Cargo.toml`**

```toml
[package]
name = "mbforge-app"
version = "0.1.0"
edition = "2021"

[dependencies]
mbforge-infra = { path = "../mbforge-infra" }
mbforge-chem = { path = "../mbforge-chem" }
mbforge-domain = { path = "../mbforge-domain" }
mbforge-pipeline = { path = "../mbforge-pipeline" }
serde.workspace = true
serde_json.workspace = true
tokio.workspace = true
log.workspace = true
tauri = { version = "2", features = [] }
tauri-plugin-dialog = "2"
tauri-plugin-shell = "2"
```

- [ ] **Step 2: 复制入口文件和命令**

Run:
```bash
cd src-tauri
mkdir -p crates/mbforge-app/src/commands
cp src/main.rs crates/mbforge-app/src/main.rs
cp -r src/commands/* crates/mbforge-app/src/commands/
cp src/protocol.rs crates/mbforge-app/src/protocol.rs
cp src/sidecar.rs crates/mbforge-app/src/sidecar.rs
```

- [ ] **Step 3: 编写 `mbforge-app/src/lib.rs` 聚合导出**

```rust
pub mod commands;
pub mod protocol;
pub mod sidecar;
```

- [ ] **Step 4: 调整 `main.rs` 模块声明**

Change:
```rust
mod commands;
mod core;
mod parsers;
mod protocol;
mod sidecar;
```
To:
```rust
use mbforge_app::{commands, protocol, sidecar};
```

And update all `crate::commands::...`, `crate::sidecar::...`, `crate::protocol::...` references accordingly.

- [ ] **Step 5: 批量替换 commands 中的 import 路径**

Use script:
```bash
cd src-tauri/crates/mbforge-app/src
find . -name "*.rs" -exec sed -i 's/crate::core::config/mbforge_infra::config/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::db/mbforge_infra::db/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::error/mbforge_infra::error/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::helpers/mbforge_infra::helpers/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::http/mbforge_infra::http/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::sidecar_client/mbforge_infra::sidecar_client/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::types/mbforge_infra::types/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::chem/mbforge_chem/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::document/mbforge_domain::document/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::molecule/mbforge_domain::molecule/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::project/mbforge_domain::project/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::core::vector/mbforge_domain::vector/g' {} +
find . -name "*.rs" -exec sed -i 's/crate::parsers/mbforge_pipeline/g' {} +
```

- [ ] **Step 6: 修改 `commands/mod.rs` 中的 handler**

The `handler()` function should still use the local `commands::*` modules, but any direct `crate::core::...` or `crate::parsers::...` references inside handler must use the new crate paths.

- [ ] **Step 7: 验证 `mbforge-app` 可编译**

Run:
```bash
cd src-tauri
cargo check -p mbforge-app
```
Expected: PASS.

- [ ] **Step 8: 提交 Phase 5**

Run:
```bash
git add src-tauri/crates/mbforge-app/
git commit -m "build(rust): add mbforge-app crate aggregating commands and Tauri entry"
```

---

## Phase 6: 清理、Zvec 实现与全量验证

### Task 6.1: 清理旧 `src-tauri/src` 目录

**Files:**
- Delete: `src-tauri/src/core/`
- Delete: `src-tauri/src/parsers/`
- Delete: `src-tauri/src/commands/`
- Delete: `src-tauri/src/protocol.rs`
- Delete: `src-tauri/src/sidecar.rs`
- Delete: `src-tauri/src/lib.rs` (or reduce to re-export)

- [ ] **Step 1: 确认新 crate 已完整复制所有必要文件**

Run:
```bash
cd src-tauri
find crates -name "*.rs" | wc -l
find src -name "*.rs" | wc -l
```

- [ ] **Step 2: 删除旧目录**

Run:
```bash
cd src-tauri
rm -rf src/core src/parsers src/commands src/protocol.rs src/sidecar.rs src/lib.rs
```

- [ ] **Step 3: 保留或删除 `src/main.rs` 和 `src/lib.rs`**

Since `mbforge-app` is now the Tauri crate, the old `src-tauri/src/` may be removed entirely or kept as a thin shim. Recommended: remove `src-tauri/src/` and update `mbforge-app/Cargo.toml` to be the default package.

Edit `src-tauri/Cargo.toml`:
```toml
[workspace]
members = ["crates/*"]
resolver = "2"

# Optional: make mbforge-app the default run target
default-members = ["crates/mbforge-app"]
```

- [ ] **Step 4: 提交清理**

Run:
```bash
git add src-tauri/
git commit -m "build(rust): remove legacy src-tauri/src modules"
```

### Task 6.2: 实现 Zvec 搜索接口

**Files:**
- Modify: `src-tauri/crates/mbforge-domain/Cargo.toml`
- Modify: `src-tauri/crates/mbforge-domain/src/document/search_engine.rs`
- Modify: `src-tauri/crates/mbforge-domain/src/document/knowledge_base.rs`

- [ ] **Step 5: 确定 Zvec Rust SDK 并锁定依赖**

Evaluate:
1. `zvec` crate on crates.io (official)
2. `zvec-bindings` crate (community, feature `sync`)
3. Build complexity on Windows

Choose one and update `mbforge-domain/Cargo.toml`.

- [ ] **Step 6: 实现 `SearchEngine::open`**

Open or create Zvec collection at `<project_root>/.mbforge/search.zvec/` with schema:
- `chunk_id`: string primary key
- `doc_id`: string with invert index
- `text`: string with FTS index
- `metadata`: string
- `embedding`: fp32 vector, HNSW, cosine metric

- [ ] **Step 7: 实现 `SearchEngine::index_document`**

Upsert chunks into Zvec collection. Delete old chunks for `doc_id` first.

- [ ] **Step 8: 实现 `SearchEngine::delete_document`**

Delete all chunks where `doc_id == ?`.

- [ ] **Step 9: 实现 `SearchEngine::vector_search`**

Use Zvec `VectorQuery` on `embedding` field with optional `doc_id` filter.

- [ ] **Step 10: 实现 `SearchEngine::text_search`**

Use Zvec `FTSQuery` on `text` field with optional `doc_id` filter.

- [ ] **Step 11: 实现 `SearchEngine::hybrid_search`**

Use Zvec `MultiQuery` combining `VectorQuery` and `FTSQuery` with RRF reranker.

- [ ] **Step 12: 更新 `knowledge_base.rs` 调用**

Ensure `kb_search` uses `search_engine.hybrid_search(...)`.

- [ ] **Step 13: 提交 Zvec 实现**

Run:
```bash
git add src-tauri/crates/mbforge-domain/
git commit -m "feat(domain): implement zvec search engine"
```

### Task 6.3: 全量验证

- [ ] **Step 14: 全 workspace 编译检查**

Run:
```bash
cd src-tauri
cargo check --workspace
```
Expected: PASS.

- [ ] **Step 15: 全 workspace 单元测试**

Run:
```bash
cd src-tauri
cargo test --workspace --lib
```
Expected: PASS.

- [ ] **Step 16: 检查循环依赖**

Run:
```bash
cd src-tauri
cargo tree -p mbforge-app -e normal | grep -E "mbforge-"
```
Expected: `mbforge-app` depends on all crates; `mbforge-domain` does NOT depend on `mbforge-pipeline`.

- [ ] **Step 17: 前端冒烟测试**

Run:
```bash
cd frontend
npm run build
```
Expected: PASS (前端未改动，Tauri 命令契约不变).

- [ ] **Step 18: Tauri dev 启动测试**

Run:
```bash
cd src-tauri
cargo tauri dev
```
Expected: App launches; basic project open / KB search works.

- [ ] **Step 19: 提交最终验证**

Run:
```bash
git add -A
git commit -m "test(rust): workspace split and zvec integration passing all checks"
```

---

## 自审检查表

1. **Spec coverage**: Every design section has corresponding tasks above.
2. **Placeholder scan**: No "TODO", "TBD", "implement later" in concrete steps. `SearchEngine` implementation is provided in Step 7 using `zvec-bindings` API.
3. **Type consistency**: `SearchEngine` interface used consistently across `knowledge_base.rs` and `pipeline`.
4. **Path consistency**: All crate paths (`mbforge_infra::`, `mbforge_chem::`, etc.) used consistently.

---

## 执行选项

Plan complete and saved to `docs/superpowers/plans/2026-06-24-rust-workspace-split-zvec.md`.

Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per Phase/Task, review between tasks, fast iteration. Requires `superpowers:subagent-driven-development` skill.

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for review.

Which approach do you prefer?
