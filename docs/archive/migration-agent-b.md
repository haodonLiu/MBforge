# Agent B：Embedding 生成 + 向量存储

## 职责

让 Rust 能自己生成 embedding 并存储到向量库，不再依赖 Python sidecar。

## 依赖

- 需要 Agent A 定义的 `SectionChunk` 类型（已存在于 `parsers/sections.rs`）
- 本 Agent 的产出被 Agent C（KnowledgeBase + Agent 工具）使用

## 任务清单

### B0：扩展 EmbedConfig

**文件**：`src-tauri/src/core/config.rs`

当前 `EmbedConfig` 缺少 `base_url` 字段。需要添加：

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmbedConfig {
    pub provider: String,
    pub model_name: String,
    pub base_url: String,    // 新增：embedding endpoint URL
    pub api_key: String,
    pub device: String,
}

impl Default for EmbedConfig {
    fn default() -> Self {
        Self {
            provider: "qwen3".into(),
            model_name: DEFAULT_EMBED_MODEL.into(),
            base_url: "http://127.0.0.1:18792".into(),  // 默认指向 sidecar
            api_key: String::new(),
            device: "cpu".into(),
        }
    }
}
```

同时在 `constants.rs` 中添加默认 embedding endpoint：

```rust
pub const DEFAULT_EMBED_BASE_URL: &str = "http://127.0.0.1:18792";
```

### B1：Embedding 生成器

**新增文件**：`src-tauri/src/core/embedding.rs`

```rust
pub struct Embedder {
    config: EmbedConfig,
    client: reqwest::Client,
}

pub struct EmbeddingResult {
    pub embeddings: Vec<Vec<f32>>,
    pub model: String,
    pub dimensions: usize,
}

impl Embedder {
    pub fn new(config: &EmbedConfig) -> Self;

    /// 生成文本 embeddings
    /// HTTP POST {base_url}/api/v1/embed
    pub async fn embed(&self, texts: &[String]) -> Result<EmbeddingResult, String>;

    /// 单条文本 embedding
    pub async fn embed_single(&self, text: &str) -> Result<Vec<f32>, String> {
        let results = self.embed(&[text.to_string()]).await?;
        results.embeddings.into_iter().next()
            .ok_or("No embedding returned".into())
    }
}
```

**HTTP 调用格式**：
```
POST {base_url}/api/v1/embed
Body: { "texts": ["text1", "text2"] }
Response: { "embeddings": [[0.1, 0.2, ...], [0.3, 0.4, ...]] }
```

**依赖**：`reqwest`（已在 Cargo.toml 中）

**测试**：
- `test_embedder_creation` — 配置解析
- `test_embed_single_mock` — mock HTTP 响应

### B2：向量存储 trait + SQLite 实现

**新增文件**：`src-tauri/src/core/vector_store.rs`

```rust
/// 向量存储 trait
pub trait VectorStore: Send + Sync {
    fn upsert(&self, id: &str, embedding: &[f32], metadata: &serde_json::Value) -> Result<(), String>;
    fn search(&self, query_embedding: &[f32], top_k: usize, filter: Option<&str>) -> Vec<SearchResult>;
    fn delete(&self, id: &str) -> Result<(), String>;
    fn delete_by_prefix(&self, prefix: &str) -> Result<(), String>;
    fn count(&self) -> usize;
}

pub struct SearchResult {
    pub id: String,
    pub score: f64,
    pub metadata: serde_json::Value,
}

/// SQLite + 暴力搜索实现（小规模足够）
pub struct SqliteVectorStore {
    db: rusqlite::Connection,
    dimension: usize,
}

impl SqliteVectorStore {
    pub fn new(path: &Path, dimension: usize) -> Result<Self, String>;
}

impl VectorStore for SqliteVectorStore { ... }
```

**存储格式**：SQLite 表
```sql
CREATE TABLE IF NOT EXISTS vectors (
    id TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,  -- f32 数组的字节表示
    metadata TEXT NOT NULL    -- JSON
);
CREATE INDEX IF NOT EXISTS idx_vectors_id ON vectors(id);
```

**相似度搜索**：读取全部向量 → 计算 cosine similarity → 排序取 top_k
（数据量 <10 万条时性能足够，后续可换 HNSW 索引）

**依赖**：`rusqlite`（已在 Cargo.toml 中）

**测试**：
- `test_upsert_and_search` — 插入 + 搜索
- `test_delete` — 删除后搜不到
- `test_cosine_similarity` — 验证相似度计算正确

### B3：KnowledgeBase 结构

**新增文件**：`src-tauri/src/core/knowledge_base.rs`

```rust
pub struct KnowledgeBase {
    vector_store: Box<dyn VectorStore>,
    tree_index: super::document_tree::DocumentTreeIndex,
    embedder: Embedder,
    project_root: PathBuf,
}

impl KnowledgeBase {
    pub fn new(project_root: &PathBuf, config: &EmbedConfig) -> Result<Self, String>;

    /// 索引文档（sections → embeddings → vector store + tree）
    pub async fn index_document(
        &self,
        doc_id: &str,
        sections: &[SectionChunk],
        page_texts: &[String],
    ) -> Result<usize, String>;

    /// 语义搜索
    pub async fn search(&self, query: &str, top_k: usize) -> Result<Vec<SearchResult>, String>;

    /// 删除文档
    pub fn remove_document(&self, doc_id: &str) -> Result<(), String>;

    /// 获取统计信息
    pub fn stats(&self) -> KbStats;
}

pub struct KbStats {
    pub document_count: usize,
    pub section_count: usize,
    pub total_vectors: usize,
}
```

**index_document 流程**：
1. 对每个 section 的 text 调 `embedder.embed_single()` 生成 embedding
2. 构建 metadata：`{doc_id, section_title, section_path, page_start, page_end}`
3. 调 `vector_store.upsert()` 存储
4. 调 `tree_index.index_document()` 保存结构树 + 页缓存

**依赖**：Agent A 的 `DocumentTreeIndex`、Agent B 自己的 `Embedder` + `VectorStore`

**测试**：
- `test_index_and_search` — 索引后能搜到
- `test_remove_document` — 删除后搜不到
- `test_stats` — 统计信息正确

### B4：注册新模块

**文件**：`src-tauri/src/core/mod.rs`

添加：
```rust
pub mod embedding;
pub mod knowledge_base;
pub mod vector_store;
```

## 验收标准

```bash
cd src-tauri
cargo test core::embedding     # Embedder
cargo test core::vector_store  # SQLite 向量存储
cargo test core::knowledge_base  # KB 索引 + 搜索
# Rust 侧能独立完成：section → embedding → vector store → 搜索
```

## 不碰的文件

- `parsers/pipeline.rs`（Agent A 的范围）
- `core/executor.rs`（Agent C 的范围）
- `core/summary.rs`（Agent C 的范围）
- `core/tools.rs`（Agent C 的范围）
