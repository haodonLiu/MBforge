# Agent C：Agent 工具 Native 化 + Summary

## 职责

把 Agent 的 9 个 Sidecar 工具转为 Rust Native 实现，加上 SummaryManager。

## 依赖

- 需要 Agent A 的 `DocumentTreeIndex`（结构树 + 页缓存）
- 需要 Agent B 的 `KnowledgeBase`（向量搜索）
- 本 Agent 的产出是 Agent D（main.rs 注册 + 前端集成）的前提

## 任务清单

### C1：SummaryManager — Rust 版

**修改文件**：`src-tauri/src/core/summary.rs`（已存在，需补全）

当前 `summary.rs` 可能是空壳或不完整。需要实现：

```rust
pub struct SummaryManager {
    project_root: PathBuf,
}

pub struct DocumentSummary {
    pub doc_id: String,
    pub l0_abstract: String,     // ~100 tokens 一句话
    pub l1_overview: String,     // ~2000 tokens 结构化概览
    pub keywords: Vec<String>,
}

impl SummaryManager {
    pub fn new(project_root: &PathBuf) -> Self;

    pub fn save(&self, doc_id: &str, summary: &DocumentSummary) -> Result<(), String>;
    pub fn load(&self, doc_id: &str) -> Option<DocumentSummary>;
    pub fn delete(&self, doc_id: &str) -> Result<(), String>;
    pub fn list(&self) -> Vec<String>;
}
```

**存储格式**：`.mbforge/summaries/{doc_id}.json`

**测试**：
- `test_save_and_load` — 写入后能读回
- `test_delete` — 删除后不存在
- `test_list` — 列出所有摘要

### C2：9 个 Sidecar 工具转 Native

**修改文件**：`src-tauri/src/core/executor.rs`

在 `register_native_tools()` 中添加新的 native 工具，替换 `register_sidecar_tools()` 中的对应项：

| 工具名 | 实现方式 | 依赖 |
|--------|---------|------|
| `search_knowledge_base` | 调 `KnowledgeBase::search()` | Agent B 的 KB |
| `get_document_structure` | 调 `DocumentTreeIndex::get_structure()` | Agent A 的 tree |
| `get_document_pages` | 调 `DocumentTreeIndex::get_pages()` | Agent A 的 tree |
| `read_document_abstract` | 调 `SummaryManager::load()` → 取 l0_abstract | Agent C 的 summary |
| `read_document_overview` | 调 `SummaryManager::load()` → 取 l1_overview | Agent C 的 summary |
| `read_document_detail` | 调 `KnowledgeBase::search()` → 取全文 | Agent B 的 KB |
| `list_molecules` | 调 `MoleculeDatabase::list_all()` | 已有 molecule_db.rs |
| `search_molecule_by_smiles` | 调 `MoleculeDatabase::search_by_smiles()` | 已有 molecule_db.rs |
| `list_documents` | 调 `Project::list_documents()` | 已有 project.rs |

**注册模式**（参考现有 6 个 native 工具）：

```rust
fn register_native_tools(registry: &mut ToolRegistry, project_root: &str) {
    // ... 现有 6 个工具 ...

    // 新增：KnowledgeBase 搜索
    let kb = KnowledgeBase::new(...);
    registry.register_with_fn(
        ToolInfo::new("search_knowledge_base", "语义搜索知识库", params),
        Box::new(move |args| {
            let query = args["query"].as_str().unwrap_or("");
            let top_k = args["top_k"].as_u64().unwrap_or(5) as usize;
            // 调 kb.search() 并序列化结果
        }),
    );

    // ... 其他 8 个工具类似 ...
}
```

**注意**：`ToolExecutor` 需要持有 `KnowledgeBase`、`DocumentTreeIndex`、`SummaryManager` 的引用。当前 `ToolExecutor::new()` 只接受 `sidecar_url` 和 `project_root`。需要扩展构造函数。

### C3：ToolExecutor 构造函数扩展

**修改文件**：`src-tauri/src/core/executor.rs`

**重要**：`ToolExecutor::new()` 被 `Agent::new()` 调用（`agent.rs:67`）。改签名会影响 Agent。

**方案**：用 Builder 模式或 Optional 参数，保持向后兼容：

```rust
pub struct ToolExecutor {
    sidecar_url: String,
    project_root: String,
    registry: ToolRegistry,
    kb: Option<KnowledgeBase>,           // 新增
    tree_index: Option<DocumentTreeIndex>, // 新增
    summary: Option<SummaryManager>,       // 新增
}

impl ToolExecutor {
    /// 原有构造函数（保持兼容，Agent 调用这个）
    pub fn new(sidecar_url: &str, project_root: &str) -> Self {
        let mut registry = ToolRegistry::new();
        Self::register_native_tools(&mut registry, project_root);
        Self::register_sidecar_tools(&mut registry);
        Self {
            sidecar_url: sidecar_url.to_string(),
            project_root: project_root.to_string(),
            registry,
            kb: None,
            tree_index: None,
            summary: None,
        }
    }

    /// 新增：带完整依赖的构造函数（index_project_rust 调用这个）
    pub fn new_with_deps(
        sidecar_url: &str,
        project_root: &str,
        kb: KnowledgeBase,
        tree_index: DocumentTreeIndex,
        summary: SummaryManager,
    ) -> Self { ... }

    /// 新增：注入依赖（Agent 初始化后调用）
    pub fn set_kb(&mut self, kb: KnowledgeBase) { self.kb = Some(kb); }
    pub fn set_tree_index(&mut self, tree: DocumentTreeIndex) { self.tree_index = Some(tree); }
    pub fn set_summary(&mut self, summary: SummaryManager) { self.summary = Some(summary); }
}
```

**Agent::new() 不需要修改** — 继续调用 `ToolExecutor::new()`，后续通过 setter 注入依赖。

### C4：Project 查询能力补齐

**修改文件**：`src-tauri/src/core/project.rs`（如果需要）

确保 `Project` 有 `list_documents()` 方法返回 `Vec<DocumentEntry>`，每个 entry 包含 `doc_id`、`path`、`doc_type`、`indexed` 等字段。

## 验收标准

```bash
cd src-tauri
cargo test core::summary       # SummaryManager
cargo test core::executor      # 工具注册 + 执行
# Agent 调用 search_knowledge_base → 返回语义搜索结果
# Agent 调用 get_document_structure → 返回 heading 树
# Agent 调用 list_molecules → 返回分子列表
```

## 不碰的文件

- `parsers/pipeline.rs`（Agent A 的范围）
- `core/embedding.rs`（Agent B 的范围）
- `core/vector_store.rs`（Agent B 的范围）
- `core/knowledge_base.rs`（Agent B 的范围）
- `main.rs`（Agent D 的范围）
