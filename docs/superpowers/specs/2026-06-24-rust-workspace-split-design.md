# MBForge Rust 后端 Workspace 拆分设计（基于 Zvec 搜索层）

> **Status**: Design pending revision approval, pending implementation plan.  
> **Date**: 2026-06-24  
> **Scope**: `src-tauri/src` 单一 crate → Cargo workspace 多 crate 拆分；同时将向量/全文搜索层从 SQLite 迁移到 **Zvec** 嵌入式向量数据库。前端（`frontend/`）与 Python sidecar（`src/mbforge/`）不在本次拆分范围内。  
> **数据策略**：不考虑旧数据迁移，面向新输入数据设计。

---

## 1. 背景与目标

### 1.1 当前问题

MBForge Rust 后端目前全部集中在 `src-tauri/src` 一个 crate 中：

- `commands/`：20+ 个 Tauri IPC 命令模块
- `core/`：8 个业务领域子目录（agent、chem、config、document、molecule、project、vector）+ 顶层基础设施模块
- `parsers/`：PDF 解析管线（pipeline、chem、pdf、ocr、structure）

所有代码共享同一个编译单元，导致：

1. **编译耦合**：修改任一模块会触发大量无关代码重编译。
2. **循环依赖风险**：`core::document::ingest_worker` 直接调用 `parsers::pipeline::*`，而 `parsers::pipeline::services::coref_persist` 又反向写入 `core::document::knowledge_base`。
3. **认知负担**：新开发者难以快速定位一个功能域的边界。
4. **并行开发困难**：多人同时修改不同领域时容易产生冲突。

### 1.2 向量存储的局限

当前 `core::vector::sqlite_vector_store.rs` 使用 SQLite BLOB + Rust 暴力余弦搜索：

- 适合小规模（<20K chunks），但扩展性差。
- 全文搜索依赖 SQLite FTS5，与向量搜索分离，需要手动 RRF 融合。
- 缺乏 ANN 索引、标量过滤、稀疏向量等现代 RAG 能力。

### 1.3 Zvec 选型理由

[Zvec](https://zvec.org/zh/docs/db/) 是阿里巴巴开源的**进程内嵌入式向量数据库**：

- **Rust 原生支持**：提供官方/社区 Rust bindings，可直接嵌入 Rust 后端。
- **无需额外服务**：进程内运行，与当前 SQLite 方案部署复杂度相同。
- **向量 + 全文一体化**：v0.5.0 原生支持 FTS 全文索引和 `MultiQuery` 混合搜索（向量 + FTS + 标量过滤 + RRF/加权融合）。
- **更高性能**：基于 Proxima 引擎，支持 HNSW/IVF/FLAT 索引，适合未来更大规模知识库。

### 1.4 设计目标

1. 按功能域拆分 Rust 后端为多个 crate，明确模块边界。
2. 消除 crate 间循环依赖，形成清晰的 DAG 依赖图。
3. 保留前端调用契约（Tauri 命令名、参数、返回值）不变。
4. 使各 crate 可独立编译、测试，降低全量构建时间。
5. 将向量/全文搜索层迁移到 Zvec，获得原生混合搜索能力。
6. 不考虑旧数据迁移，新架构面向未来输入数据设计。

---

## 2. 方案选择

本次设计考虑过三种方案：

| 方案 | 做法 | 优点 | 缺点 | 结论 |
|------|------|------|------|------|
| A. 目录重组 | 保持单一 crate，按功能域重排 `src/` 目录 | 改动小、风险低 | 未真正解耦编译，循环依赖仍存在 | 放弃 |
| **B. Workspace 拆分 + Zvec** | **引入 Cargo workspace，拆为 5 个 crate；搜索层迁 Zvec** | **独立编译、强制解耦、现代检索能力** | **需要一次中等规模重构 + 引入 C++ 构建依赖** | **采用** |
| C. 完全服务化 | 每个领域拆成独立服务 crate | 边界最清晰 | 过度设计，抽象成本高 | 放弃 |

最终采用 **方案 B**。

---

## 3. 最终 Workspace 结构

```text
src-tauri/
├── Cargo.toml                 # workspace 根
├── crates/
│   ├── mbforge-app/           # Tauri 应用入口 + 命令聚合
│   │   └── src/
│   │       ├── main.rs        # 启动、sidecar、状态管理
│   │       ├── lib.rs
│   │       ├── commands/      # 所有 #[tauri::command]
│   │       ├── protocol.rs    # URI scheme 协议
│   │       └── sidecar.rs     # Python sidecar 管理
│   │
│   ├── mbforge-domain/        # 核心业务状态
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── agent/         # Agent 会话、ReAct、memory、trajectory
│   │       ├── molecule/      # 分子 DB、engine、dedup、cluster、store
│   │       ├── document/      # KB、tree、semantic cache、search engine
│   │       │   ├── knowledge_base.rs   # SQLite：coref、file_cache、tree
│   │       │   ├── search_engine.rs    # Zvec：向量 + FTS + 混合搜索
│   │       │   ├── document_tree.rs
│   │       │   ├── file_cache.rs
│   │       │   ├── semantic_cache.rs
│   │       │   └── stream_search.rs
│   │       ├── ingest_queue/  # 纯 SQLite 队列 CRUD（无 pipeline 依赖）
│   │       ├── vector/        # Embedding 客户端/类型（可选，若 zvec 负责存储则变薄）
│   │       └── project/       # Project、DocumentProject、resource_manager
│   │
│   ├── mbforge-chem/          # 纯化学计算
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── smiles.rs
│   │       ├── esmiles.rs
│   │       ├── molecode.rs
│   │       ├── markush.rs
│   │       ├── sar.rs
│   │       └── gesim.rs
│   │
│   ├── mbforge-pipeline/      # PDF 解析管线 + 编排
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── ingest_worker/ # 原 core/document/ingest_worker.rs
│   │       ├── pipeline/      # runner / context / stages / services
│   │       ├── chem/
│   │       ├── pdf/
│   │       ├── ocr/
│   │       ├── structure/
│   │       └── doc_types.rs
│   │
│   └── mbforge-infra/         # 基础设施
│       └── src/
│           ├── lib.rs
│           ├── db.rs          # SQLite 连接管理
│           ├── error.rs       # AppError / AppResult
│           ├── helpers.rs     # 路径安全、JSON 工具
│           ├── http.rs        # HTTP client 工厂
│           ├── sidecar_client.rs
│           ├── types.rs
│           └── config/        # 常量、配置
│
└── tests/                     # workspace 级集成测试
```

---

## 4. 依赖规则（DAG）

```text
                    mbforge-app
                  /      |      \
                 /       |       \
    mbforge-pipeline ◄───┘       └─► mbforge-domain
          │                               │
          │         (ingest_queue)        │
          │                               │
          └─────────────┬─────────────────┘
                        │
                  mbforge-chem
                        │
                  mbforge-infra
```

### 4.1 硬性规则

1. **`mbforge-infra`**：只能被依赖，不能依赖任何业务 crate。
2. **`mbforge-chem`**：只依赖 `mbforge-infra`，以纯函数为主，无状态。
3. **`mbforge-domain`**：依赖 `mbforge-chem` + `mbforge-infra`，**禁止依赖 `mbforge-pipeline`**。
4. **`mbforge-pipeline`**：依赖 `mbforge-domain` + `mbforge-chem` + `mbforge-infra`，是业务消费方。
5. **`mbforge-app`**：聚合所有 crate，所有 Tauri IPC 命令在此注册。

### 4.2 循环依赖解除说明

**原问题**：

- `core::document::ingest_worker` 调用 `parsers::pipeline::*`。
- `parsers::pipeline::services::coref_persist` 反向写入 `core::document::knowledge_base`。
- 若两者同处一个 crate，形成 `domain → pipeline → domain` 循环。

**解除方式**：

- `ingest_worker` 上移到 `mbforge-pipeline`，作为 pipeline 的入口编排器。
- `mbforge-pipeline` 合法依赖 `mbforge-domain`（domain 是底层业务服务）。
- `mbforge-domain` 不再依赖 pipeline，只暴露公共 API。
- `ingest_queue` 作为纯状态层留在 `mbforge-domain`。

---

## 5. 关键文件归属

| 当前路径 | 新位置 | 原因 |
|----------|--------|------|
| `core/document/ingest_worker.rs` | `mbforge-pipeline::ingest_worker` | 编排器，调用 pipeline 各阶段 |
| `core/document/ingest_queue.rs`（如有） | `mbforge-domain::ingest_queue` | 纯队列 CRUD |
| `core/project/resource_manager.rs` | `mbforge-domain::project::resource_manager` | 项目管理的一部分 |
| `commands/*` | `mbforge-app::commands` | 纯 Tauri IPC 胶水 |
| `core/molecule/*` | `mbforge-domain::molecule` | 分子业务 |
| `core/document/knowledge_base.rs` | `mbforge-domain::document::knowledge_base` | SQLite 业务表（coref/file_cache/tree/semantic_cache） |
| `core/vector/sqlite_vector_store.rs` | **删除** | 由 Zvec 替代 |
| `core/vector/embedding.rs` | `mbforge-domain::vector::embedding` 或 `mbforge-domain::document::search_engine` | Embedding 客户端调用 |
| `parsers/pipeline/services/coref_persist.rs` | `mbforge-pipeline::pipeline::services::coref_persist` | 解析管线服务，通过 domain 公共 API 写入 KB |
| `parsers/*` 其余 | `mbforge-pipeline::*` | 解析管线整体 |
| `core/chem/*` | `mbforge-chem::*` | 化学计算 |
| `core/{db,error,helpers,types,http,sidecar_client,config}` | `mbforge-infra::*` | 基础设施 |
| `main.rs` | `mbforge-app::main` | Tauri 入口 |
| `protocol.rs` | `mbforge-app::protocol` | URI scheme |
| `sidecar.rs` | `mbforge-app::sidecar` | sidecar 管理 |

---

## 6. Zvec 搜索层设计

### 6.1 职责划分

| 存储 | 负责模块 | 数据 |
|------|----------|------|
| **Zvec Collection** | `mbforge-domain::document::search_engine` | chunk_id, doc_id, text, metadata, embedding；向量索引 + FTS 索引 |
| **SQLite (`knowledge_base.db`)** | `mbforge-domain::document::knowledge_base` | coref 标注、file_cache、document_tree、semantic_cache 等业务表 |

### 6.2 `SearchEngine` 接口

```rust
// mbforge-domain::document::search_engine

pub struct SearchEngine {
    collection: zvec::Collection,  // 或社区 binding 的线程安全封装
    dim: usize,
}

pub struct SearchResult {
    pub id: String,        // chunk_id
    pub text: String,
    pub metadata: serde_json::Value,
    pub score: f32,
}

impl SearchEngine {
    /// 打开或创建 Zvec collection
    pub fn open(path: &Path, dim: usize) -> AppResult<Self>;

    /// 索引/重新索引一个文档的全部 chunks
    pub fn index_document(
        &self,
        doc_id: &str,
        chunk_ids: &[String],
        texts: &[String],
        metadatas: &[String],
        embeddings: &[Vec<f32>],
    ) -> AppResult<()>;

    /// 删除一个文档的所有 chunks
    pub fn delete_document(&self, doc_id: &str) -> AppResult<()>;

    /// 纯向量搜索
    pub fn vector_search(
        &self,
        query_embedding: &[f32],
        top_k: usize,
        doc_id_filter: Option<&str>,
    ) -> AppResult<Vec<SearchResult>>;

    /// 纯全文搜索
    pub fn text_search(
        &self,
        query: &str,
        top_k: usize,
        doc_id_filter: Option<&str>,
    ) -> AppResult<Vec<SearchResult>>;

    /// 混合搜索：向量 + FTS + RRF/加权融合
    pub fn hybrid_search(
        &self,
        query_embedding: &[f32],
        query_text: &str,
        top_k: usize,
        doc_id_filter: Option<&str>,
    ) -> AppResult<Vec<SearchResult>>;

    pub fn count(&self) -> AppResult<usize>;
}
```

### 6.3 Zvec Collection Schema

```rust
let mut schema = CollectionSchema::builder("mbforge_kb")?
    .field(FieldSchema::string("chunk_id").primary_key(true))?
    .field(FieldSchema::string("doc_id").invert_index(true, false))?
    .field(FieldSchema::string("text").fts_tokenizer("standard"))?
    .field(FieldSchema::string("metadata"))?
    .field(
        FieldSchema::vector_fp32("embedding", dim)
            .hnsw(16, 200)
            .metric(MetricType::Cosine),
    )?
    .build()?;
```

### 6.4 `KnowledgeBase` 的变化

- 删除 `vector_store: SqliteVectorStore`。
- 删除 `sections_fts` 虚拟表。
- 删除 `reciprocal_rank_fusion`（zvec 原生支持）。
- 新增 `search_engine: SearchEngine`。
- `kb_search` 改为调用 `search_engine.hybrid_search(...)`。
- SQLite 连接继续保留，用于 coref / file_cache / document_tree / semantic_cache 等业务表。

---

## 7. 公共类型与接口安排

### 7.1 下沉到 `mbforge-infra`

以下类型/模块被多个上层 crate 共用：

- `AppError`、`AppResult`、`ErrorCode`
- `db::open_db`、`db::SharedConn` 等数据库连接工具
- `helpers::assert_within_root`、`helpers::safe_join`、`helpers::load_json`、`helpers::save_json`
- `sidecar_client::SidecarClient`
- `http::shared_client`
- `config::constants`
- `types` 中跨边界的数据结构（如 `DocumentClassification`、`ActivityData`、`SearchResult` 等）

### 7.2 留在 `mbforge-domain`

以下类型属于业务领域：

- `KnowledgeBase` 及其业务方法
- `SearchEngine` 及 Zvec 封装
- `MoleculeDatabase`、`MoleculeEngine`
- `Project`、`DocumentProject`
- `IngestQueue` 表操作

### 7.3 `mbforge-pipeline` 的调用方式

`mbforge-pipeline` 通过 `mbforge-domain` 的公共 API 写入结果：

```rust
use mbforge_domain::document::knowledge_base::KnowledgeBase;
use mbforge_domain::document::search_engine::SearchEngine;
use mbforge_domain::molecule::molecule_store::MoleculeDatabase;
```

禁止 `mbforge-pipeline` 直接访问 `mbforge-domain` 内部私有模块。

---

## 8. 迁移路径

推荐按以下顺序执行，每阶段结束后至少保证 `cargo check` 通过：

### Phase 1：抽出 `mbforge-infra`

- 新建 `crates/mbforge-infra`。
- 迁移 `core::{db, error, helpers, types, http, sidecar_client, config}`。
- 全项目引用改为 `mbforge_infra::`。
- 验证 `cargo check`。

### Phase 2：抽出 `mbforge-chem`

- 新建 `crates/mbforge-chem`。
- 迁移 `core::chem`。
- 仅依赖 `mbforge-infra`。
- 同步迁移 `commands::chem_ops` 中的纯计算调用。
- 验证 `cargo check`。

### Phase 3：重构 `mbforge-domain`

- 新建 `crates/mbforge-domain`。
- 迁移 `core::{agent, molecule, document, vector, project}`。
- 新增 `ingest_queue` 模块（如有）。
- **关键改动**：在 `document` 下新增 `search_engine.rs`，使用 Zvec 实现向量+FTS+混合搜索；删除 `sqlite_vector_store.rs`。
- `knowledge_base.rs` 保留 SQLite 业务表，删除向量/FTS 相关代码。
- 确保不依赖 `parsers`。
- 验证 `cargo check`。

### Phase 4：重构 `mbforge-pipeline`

- 新建 `crates/mbforge-pipeline`。
- 迁移 `parsers::*`。
- 迁移 `core::document::ingest_worker` 到 `mbforge-pipeline::ingest_worker`。
- `pipeline` 通过 `mbforge-domain` 公共 API 写入结果（包括 `SearchEngine::index_document`）。
- 验证 `cargo check`。

### Phase 5：重构 `mbforge-app`

- 新建 `crates/mbforge-app`。
- 迁移 `main.rs`、`commands/`、`protocol.rs`、`sidecar.rs`。
- 在 `Cargo.toml` 中聚合所有 workspace member。
- 验证 `cargo check`。

### Phase 6：清理与测试

- 删除旧 `src-tauri/src/` 顶层模块。
- 运行 `cargo check --workspace`。
- 运行 `cargo test --workspace`。
- 修复剩余引用和路径问题。

---

## 9. 风险与回退策略

### 9.1 主要风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 循环依赖拆分困难 | 某些 domain/pipeline 边界不清晰 | 每 Phase 结束后 `cargo check`，遇到循环时回退并引入 trait 抽象 |
| Zvec 构建依赖 | 需要 C++17 + CMake，首次构建长 | 在 `README` 中明确环境要求；CI 中预装 CMake/MSVC；尝试 `bundled` feature 减少用户手动配置 |
| Zvec Rust API 不稳定 | v0.5.0 较新，API 可能变化 | 用 `SearchEngine` 封装隔离，API 变化只改一处 |
| 搜索结果差异 | zvec 的 RRF/FTS 与当前实现行为不同 | 重新校准 `top_k` 放大系数；在测试中覆盖常见查询 |
| Zvec 与 SQLite 双写一致性 | 删除文档需同时清理两边 | 删除操作幂等化：先删 Zvec，再删 SQLite；失败可重试 |
| Tauri 命令注册出错 | 前端调用失败 | 保持命令名、参数、返回值不变；迁移后跑前端冒烟测试 |

### 9.2 回退策略

- 每个 Phase 单独提交 Git，便于单步回滚。
- 若 Zvec 集成遇到阻塞，可在 `SearchEngine` 中保留一个 SQLite fallback 实现作为退路（但不作为默认）。
- 保持前端契约不变，确保后端重构不影响 UI。

---

## 10. 后续可选扩展

### 10.1 `mbforge-chem` 独立 CLI

`mbforge-chem` 设计为纯计算库，未来可轻松扩展为独立 CLI 工具：

```text
mbforge-chem/
├── src/
│   ├── lib.rs          # 库入口
│   └── ...             # 化学计算模块
└── src/bin/
    └── mbforge-chem.rs # CLI 入口
```

首批建议支持的命令：

- `mbforge-chem canonicalize <smiles>`
- `mbforge-chem esmiles --from-smiles <smiles>`
- `mbforge-chem molecode <smiles>`
- `mbforge-chem substructure --query <smarts> --inputs <file>`

该扩展不影响当前 workspace 拆分，可在 Phase 2 完成后或整体拆分完成后再做。

### 10.2 OCR 后端独立服务

`mbforge-pipeline::ocr` 未来可进一步拆分为独立 HTTP/gRPC 服务，但当前阶段收益不明显，不建议在本次拆分中实施。

---

## 11. 验收标准

1. `src-tauri` 转为 Cargo workspace，包含 5 个 crate。
2. `cargo check --workspace` 零 error。
3. `cargo test --workspace` 通过。
4. 前端 Tauri 调用无需修改即可正常工作。
5. crate 间无循环依赖（可通过 `cargo tree` 验证）。
6. 每个 crate 职责单一，可被独立理解和测试。
7. `SearchEngine` 使用 Zvec 完成向量搜索、全文搜索、混合搜索。
8. `knowledge_base.rs` 中不再包含向量/FTS 相关 SQLite 代码。

---

## 12. 决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| Workspace 还是单 crate 目录重组 | Workspace | 真正解耦编译，强制消除循环依赖 |
| `commands` 放 app 还是分散到各 crate | 放 `mbforge-app` | 避免业务 crate 依赖 tauri，保持解耦 |
| `resource_manager` 放 domain 还是独立 crate | 放 `mbforge-domain` | 体量小，属于项目管理的一部分 |
| `ingest_worker` 放 domain 还是 pipeline | 放 `mbforge-pipeline` | 它是编排器，调用 pipeline 各阶段，避免 domain → pipeline 循环 |
| `ingest_queue` 放 domain 还是 pipeline | 放 `mbforge-domain` | 纯 SQLite CRUD，被 app 和 pipeline 共用 |
| 向量/全文存储：SQLite 还是 Zvec | **Zvec** | 原生混合搜索、ANN 索引、现代 RAG 能力 |
| 是否迁移旧数据 | **否** | 面向未来输入数据设计，简化架构 |
| Zvec 负责范围 | 向量 + FTS + 混合搜索 | coref/文件缓存/树等业务表仍由 SQLite 负责 |
| 是否本次做 chem CLI | 否 | 先完成 workspace 拆分，CLI 作为后续扩展 |

---

*Design pending final approval. Next step: user review → spec self-review → implementation plan via `writing-plans` skill.*
