# Agent D：Tauri 命令注册 + KB 索引端点 + 前端集成 + 清理

## 职责

把 A/B/C 三个 Agent 的产出接入 Tauri 命令系统、Python sidecar KB 端点、前端调用，最后清理 Python 代码。

## 依赖

- Agent A 的 `DocumentTreeIndex` + 扩展后的 `PdfParseResult`
- Agent B 的 `KnowledgeBase` + `Embedder`
- Agent C 的 `ToolExecutor` 扩展 + `SummaryManager`
- 本 Agent 是最后一个执行的，负责整合

## 任务清单

### D1：Tauri 命令注册

**修改文件**：`src-tauri/src/main.rs`

在 `invoke_handler` 中新增/修改命令：

```rust
.invoke_handler(tauri::generate_handler![
    // ... 现有命令 ...

    // 新增：项目索引（替代 Python /index）
    parsers::pipeline::index_project_rust,

    // 新增：知识库查询
    core::knowledge_base::kb_search,
    core::knowledge_base::kb_get_structure,
    core::knowledge_base::kb_get_pages,
])
```

**新增命令实现**：

```rust
// parsers/pipeline.rs 中
#[tauri::command]
pub async fn index_project_rust(
    app: AppHandle,
    root: String,
) -> Result<IndexResult, String> {
    // 1. 打开项目
    // 2. 找到未索引的 PDF
    // 3. 对每个 PDF 调 process_document()
    // 4. 调 KnowledgeBase::index_document()
    // 5. 返回统计结果
}

pub struct IndexResult {
    pub indexed: usize,
    pub sections: usize,
    pub errors: Vec<String>,
}
```

### D2：Python sidecar KB 端点保留（过渡期）

**修改文件**：`src/mbforge/model_server/routers/kb.py`

保留 `/kb/index-sections` 端点（Agent B 的 Rust KB 尚未完全替代时使用）。当 Rust KB 稳定后，这个端点可以删除。

**修改文件**：`src/mbforge/model_server/routers/project.py`

移除 `/index` 和 `/index-stream` 端点（已被 Rust `index_project_rust` 替代）。

### D3：前端调用更新

**修改文件**：`frontend/src/api/tauri-bridge.ts`

新增 Rust 命令的 TypeScript wrapper：

```typescript
export async function indexProjectRust(root: string): Promise<IndexResult> {
  return invoke<IndexResult>('index_project_rust', { root })
}

export async function kbSearch(projectRoot: string, query: string, topK = 5) {
  return invoke<SearchResult[]>('kb_search', { projectRoot, query, topK })
}

export async function kbGetStructure(projectRoot: string, docId: string) {
  return invoke<TreeNode[]>('kb_get_structure', { projectRoot, docId })
}

export async function kbGetPages(projectRoot: string, docId: string, pages: string) {
  return invoke<PageContent[]>('kb_get_pages', { projectRoot, docId, pages })
}
```

**修改文件**：`frontend/src/components/ProjectView.tsx`

将 "索引项目" 按钮的调用从 `indexProjectStream()`（Python sidecar）改为 `indexProjectRust()`（Rust Tauri command）。

### D4：Python 代码清理（分两轮）

**第一轮（立即执行）**：
- `project.py` 的 `/index` 和 `/index-stream` 端点 → 删除（已被 Rust `index_project_rust` 替代）
- `cli.py` 的 `_cmd_index` → 已是 stub，保持

**第二轮（Rust KB 稳定后执行，本 Agent 不做）**：
- `core/knowledge_base.py` → 删除（被 Rust KnowledgeBase 替代）
- `core/summarizer.py` → 删除（被 Rust SummaryManager 替代）
- `model_server/routers/kb.py` 的 `/kb/index-sections` → 删除

**始终保留的 Python 代码**：
- `model_server/` — LLM/VLM/Embedder sidecar（模型推理仍需 Python）
- `parsers/molecule/mol_image_pipeline.py` — MolDetv2/MolScribe（深度学习模型，保留 Python）
- `model_server/routers/kb.py` — 过渡期保留，直到 Rust KB 完全验证

### D5：main.rs setup 改造

**修改文件**：`src-tauri/src/main.rs` 的 `setup` 闭包

当前 setup 会启动 Python sidecar 进程。改为可选：

```rust
.setup(|app| {
    // 只在需要时启动 Python sidecar
    if std::env::var("MBFORGE_NO_SPAWN").is_err() {
        // 启动 Python sidecar
    }
    // 初始化 Rust KnowledgeBase
    // 初始化 Rust SummaryManager
    // 注入到 AgentState
    Ok(())
})
```

### D6：数据迁移策略

**问题**：用户已有的 ChromaDB 数据（`.mbforge/chroma_db/`）需要迁移到 Rust 的 SQLite 向量存储。

**方案**：在 `KnowledgeBase::new()` 中检测旧数据并自动迁移：

```rust
impl KnowledgeBase {
    pub fn new(project_root: &PathBuf, config: &EmbedConfig) -> Result<Self, String> {
        let chroma_path = project_root.join(".mbforge/chroma_db");
        let sqlite_path = project_root.join(".mbforge/vectors.db");

        // 检测旧数据
        if chroma_path.exists() && !sqlite_path.exists() {
            Self::migrate_from_chromadb(&chroma_path, &sqlite_path, config)?;
        }

        // 正常初始化
        ...
    }

    fn migrate_from_chromadb(chroma_path: &Path, sqlite_path: &Path, config: &EmbedConfig) -> Result<(), String> {
        // 1. 读取 ChromaDB 的 collection 数据
        // 2. 对每条记录：提取 text + metadata
        // 3. 调 Embedder 生成 embedding
        // 4. 写入 SQLite vector store
        // 5. 重命名旧目录为 .mbforge/chroma_dbBackup
    }
}
```

**注意**：这个迁移只在首次启动时执行一次。迁移完成后旧目录保留为备份。

## 验收标准

```bash
cd src-tauri && cargo build  # 编译通过
cd frontend && npx tsc --noEmit  # TypeScript 类型检查通过

# 端到端测试：
# 1. 前端点击"索引项目" → 调 Rust index_project_rust
# 2. PDF 被解析 → sections 生成 → embeddings → 向量存储
# 3. Agent 搜索 → 返回带 section 路径和页码的结果
# 4. Python sidecar 不再被 PDF 管道调用
```

## 不碰的文件

- `parsers/headings.rs`（Agent A）
- `parsers/sections.rs`（Agent A）
- `core/embedding.rs`（Agent B）
- `core/vector_store.rs`（Agent B）
- `core/knowledge_base.rs`（Agent B）
- `core/summary.rs`（Agent C）
- `core/executor.rs`（Agent C）
