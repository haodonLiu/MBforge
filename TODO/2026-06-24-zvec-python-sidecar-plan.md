# Zvec 集成实施计划（Python Sidecar 方案）

> 日期：2026-06-24  
> 决策：Rust 直接绑定 `zvec-rust` 在当前 Windows 开发环境受阻塞（CMake 4.x 兼容性、Boost/Arrow 子模块 SSL 下载失败、预编译库 GitHub Release 下载慢），改为在现有 Python FastAPI sidecar 中集成 Zvec Python SDK，Rust 通过 HTTP 调用。

## 现状

- Python `.venv` 已成功安装 `zvec==0.5.1`（有 Windows wheel）。
- Rust 侧 `mbforge-domain` 当前使用本地 `zvec-bindings` stub 维持编译；真实搜索逻辑待接入。
- 向量、全文、混合搜索将统一由 Zvec collection 承担，替代原 SQLite FTS5 + 自定义向量缓存。

## 实施步骤

1. **Python sidecar 新增 Zvec 服务模块**
   - 路径建议：`src/mbforge/zvec_service.py` 或 `src/mbforge/backends/zvec_backend.py`
   - 职责：
     - collection 生命周期管理（open/close/create）
     - chunk upsert / delete by doc_id
     - vector search、text search (BM25)、hybrid search (multi-query + RRF)
   - 配置：collection 路径、embedding dim、默认索引（HNSW + Cosine）、FTS tokenizer（standard/jieba）

2. **FastAPI 端点**
   - `POST /api/v1/zvec/collection/open`
   - `POST /api/v1/zvec/index`
   - `POST /api/v1/zvec/delete`
   - `POST /api/v1/zvec/search/vector`
   - `POST /api/v1/zvec/search/text`
   - `POST /api/v1/zvec/search/hybrid`
   - 统一返回 `{success: bool, data?: ..., error?: ...}`

3. **Rust HTTP client 封装**
   - 在 `mbforge-domain` 中改造 `SearchEngine`：
     - 保留现有公共接口（`open`, `index_document`, `delete_document`, `vector_search`, `text_search`, `hybrid_search`, `count`）
     - 内部通过 `mbforge_infra::http` / `sidecar_client` 调用上述端点
     - 移除对本地 `zvec-bindings` stub 的依赖（后续可删除 `crates/zvec-bindings`）

4. **数据模型对齐**
   - Document fields: `chunk_id` (pk), `doc_id` (filter invert index), `text` (FTS), `metadata` (json string)
   - Vector: `embedding` (VECTOR_FP32, dim 由配置决定)

5. **测试**
   - Python：`tests/unit/test_zvec_service.py` 覆盖 open/insert/query/delete
   - Rust：`tests/zvec_sidecar_integration.rs` 在 sidecar 启动后做端到端搜索验证

6. **文档与清理**
   - 更新 `AGENTS.md` / `docs/specs/architecture-conventions.md` 中的向量存储说明
   - 删除 `crates/zvec-bindings` stub 与 workspace patch
   - 清理 `.zvec-lib`、`.zvec-src` 等临时目录

## 接口草案（Rust → Python）

```rust
// mbforge-domain SearchEngine 保持公共 API 不变
pub fn open(path: &Path, dim: usize) -> AppResult<Self>;
pub fn index_document(&self, doc_id, chunk_ids, texts, metadatas, embeddings) -> AppResult<()>;
pub fn delete_document(&self, doc_id) -> AppResult<()>;
pub fn vector_search(&self, query_embedding, top_k, doc_id_filter) -> AppResult<Vec<SearchResult>>;
pub fn text_search(&self, query, top_k, doc_id_filter) -> AppResult<Vec<SearchResult>>;
pub fn hybrid_search(&self, query_vec, query_text, top_k, doc_id_filter) -> AppResult<Vec<SearchResult>>;
```

Python 端对应接收 JSON，调用 `collection.query(...)` 并返回命中的 `id`, `score`, `text`, `metadata`。

## 风险与注意点

- **运行时依赖**：Zvec Python wheel 包含本地动态库，需确保打包/分发时 DLL 可达。
- **并发**：Zvec collection 写操作是单进程独占；sidecar 内部需串行化写请求或使用文件锁。
- **迁移**：旧 SQLite 向量/FTS 数据本次不迁移，新数据直接进入 Zvec；关系型数据仍存 SQLite。
- **FTS 与向量互斥**：Zvec 单个 Query 不能同时设置 vector 和 fts；hybrid 必须用 multi-query + reranker 实现。
