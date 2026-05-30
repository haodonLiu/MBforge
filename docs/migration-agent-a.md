# Agent A：数据结构 + Pipeline 整合

## 职责

补齐 Rust 侧的数据结构，让 `process_document()` 输出完整的 section 化数据。

## 依赖

无外部依赖。本 Agent 的产出是其他 3 个 Agent 的基础。

## 共享接口契约

本 Agent 定义的类型是其他 Agent 的基础，必须严格遵守：

```rust
// parsers/sections.rs（已有，确认导出）
pub struct SectionChunk {
    pub title: String,
    pub path: String,
    pub text: String,
    pub page_start: Option<usize>,
    pub page_end: Option<usize>,
    pub line_start: usize,
    pub line_end: usize,
}

// core/document_tree.rs（本 Agent 新增）
pub struct DocumentTreeIndex { project_root: PathBuf }
pub struct PageContent { pub page: usize, pub content: String }

// DocumentTreeIndex 的公开 API（Agent B/C 会调用）：
// fn index_document(doc_id, sections, page_texts) -> Result<(), String>
// fn get_structure(doc_id) -> Option<Vec<TreeNode>>
// fn get_pages(doc_id, pages_str) -> Vec<PageContent>
// fn remove_document(doc_id) -> Result<(), String>
```

## 任务清单

### A1：扩展 DocProcessingContext

**文件**：`src-tauri/src/parsers/types.rs`

`process_document()` 返回 `()`，不返回 `PdfParseResult`。sections 应该存到 `DocProcessingContext`：

```rust
pub struct DocProcessingContext {
    // --- 现有字段 ---
    pub source_path: PathBuf,
    pub parser_used: String,
    pub raw_text: String,
    pub images: Vec<ImageRef>,
    pub page_count: usize,
    pub doc_type: Option<String>,
    pub user_request: String,

    // --- 新增字段 ---
    pub headings: Vec<super::headings::Heading>,
    pub sections: Vec<super::sections::SectionChunk>,
    pub page_texts: Vec<String>,
}
```

**同样扩展 `PdfParseResult`**（`parse_pdf` 命令的返回值）：

```rust
pub struct PdfParseResult {
    // --- 现有字段（不动）---
    pub content: String,
    pub classification: DocumentClassification,
    pub chunks: Vec<String>,
    pub esmiles: Vec<String>,
    pub activities: Vec<ActivityData>,
    pub parser: String,
    pub page_count: usize,
    pub images: Vec<ImageRef>,

    // --- 新增字段 ---
    pub headings: Vec<super::headings::Heading>,
    pub sections: Vec<super::sections::SectionChunk>,
    pub page_texts: Vec<String>,
}
```

**测试**：serde round-trip。

### A2：Heading 加 Serialize/Deserialize

**文件**：`src-tauri/src/parsers/headings.rs`

```rust
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Heading {
    pub level: usize,
    pub title: String,
    pub line_num: usize,
}
```

### A3：Pipeline 整合 — process_document 输出 sections

**文件**：`src-tauri/src/parsers/pipeline.rs`

在 `process_document()` 的 Stage 0 之后，Stage 1 之前，插入 section 构建：

```rust
// Stage 0.5: 构建 sections
let headings = crate::parsers::headings::extract_headings(&ctx.raw_text);
let sections = crate::parsers::sections::build_sections(
    &ctx.raw_text, &headings, None, 8000
);
ctx.headings = headings;
ctx.sections = sections;
```

**同样修改 `parse_pdf()`**：在 Stage 2 之后插入 section 构建，填充到 PdfParseResult。

### A4：DocumentTreeIndex — 结构树 + 页缓存持久化

**新增文件**：`src-tauri/src/core/document_tree.rs`

```rust
pub struct DocumentTreeIndex {
    project_root: PathBuf,
}

impl DocumentTreeIndex {
    pub fn new(project_root: &PathBuf) -> Self;

    /// 索引文档：保存结构树 + 页缓存
    pub fn index_document(
        &self,
        doc_id: &str,
        sections: &[SectionChunk],
        page_texts: &[String],
    ) -> Result<(), String>;

    /// 获取文档结构树（不含正文，用于 Agent 导航）
    pub fn get_structure(&self, doc_id: &str) -> Option<Vec<TreeNode>>;

    /// 获取指定页码的原文
    pub fn get_pages(&self, doc_id: &str, pages: &str) -> Vec<PageContent>;

    /// 删除文档索引
    pub fn remove_document(&self, doc_id: &str) -> Result<(), String>;
}

pub struct PageContent {
    pub page: usize,
    pub content: String,
}
```

**存储格式**：
- 结构树：`.mbforge/doc_trees.json` — `{doc_id: TreeNode[]}` 的 JSON
- 页缓存：`.mbforge/pages/{doc_id}/page_{i}.txt` — 每页一个文件

**测试**：
- `test_index_document` — 写入后能读回结构树
- `test_get_pages` — 按页码范围读取
- `test_remove_document` — 清理文件

### A5：注册新模块

**文件**：`src-tauri/src/core/mod.rs`

添加 `pub mod document_tree;`

## 验收标准

```bash
cd src-tauri
cargo test parsers::headings  # Heading serde
cargo test parsers::sections  # SectionChunk 构建
cargo test core::document_tree  # 树 + 页缓存持久化
# process_document() 的 ctx 包含 headings + sections + page_texts
# parse_pdf() 的返回值包含 headings + sections + page_texts
```

## 不碰的文件

- `core/executor.rs`（Agent C 的范围）
- `core/knowledge_base.rs`（Agent B 的范围）
- `core/summary.rs`（Agent C 的范围）
- `core/tools.rs`（Agent C 的范围）
- `core/config.rs`（Agent B 的范围）
