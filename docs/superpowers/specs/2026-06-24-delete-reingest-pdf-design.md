# PDF/文献删除与重新读取功能设计

> 状态：已通过 brainstorming，等待实现计划  
> 日期：2026-06-24  
> 关联需求：允许删除已经读取后的 PDF 以及相关数据；允许重新读取已有文献。

---

## 1. 背景与目标

当前 MBForge 导入 PDF 后会生成大量派生数据：

- 文本/报告 Markdown
- 分子记录、分子关系、检测索引
- 向量、FTS5 索引、文档结构树
- coref 标注、文件解析缓存、ingest queue 任务
- 摘要、截图缓存

用户需要能够：

1. **彻底删除**已读取的 PDF 及其所有派生数据。
2. **重新读取**已有文献，即保留原始 PDF，清空所有派生数据后重新走一遍 ingestion 流程。

本设计不处理 coref 模型的重新训练，也不引入批量操作（后续可扩展）。

---

## 2. 设计决策

| 问题 | 决策 |
|------|------|
| 删除范围 | 彻底删除 `source.pdf` + `DocumentProject` 目录 + 所有数据库/缓存关联数据 |
| 重新读取范围 | 保留 `source.pdf` 和 `.mbforge/index.json`，清空其余派生数据，重新入队 |
| 重新读取时手动数据 | 全部清空，视为全新文档 |
| 操作入口 | 文献列表每行行内图标按钮：↻ 重新读取、🗑 删除 |
| 实现结构 | 统一 `cleanup_document_data` 清理逻辑；`delete` 和 `reingest` 作为薄命令包装 |
| 确认机制 | 二次确认对话框，防止误操作 |

---

## 3. 后端设计

### 3.1 新增核心函数：`Project::cleanup_document_data(doc_id, keep_source)`

位置：`src-tauri/src/core/project/project.rs`

职责：删除指定文档的所有派生数据，可选择是否保留原始 PDF。

清理顺序与范围：

1. **取消运行中的任务**
   - 若该 doc 在 ingest queue 中有运行中任务，先调用 `ingest_cancel`。

2. **molecules.db 清理**
   - 按 `source_doc = doc_id` 查询所有 `mol_id`。
   - 删除 `molecule_images`（关联 `mol_id`）。
   - 删除 `molecule_relations`（`mol_a_id` 或 `mol_b_id` 在目标列表中）。
   - 删除 `molecule_detections`（`doc_id`）。
   - 删除 `molecules` 行。

3. **knowledge_base.db 清理**
   - 调用 `kb.remove_document(doc_id)`：删除 `vectors`、`sections_fts`、文档结构树。
   - 删除 `figure_labels` 和 `coref_predictions`（`doc_id`）。
   - 删除 `file_cache` 中该 source 路径的条目。
   - 删除 `ingest_queue` 中该 doc 的所有任务记录。

4. **文件系统清理**
   - 删除 `DocumentProject` 目录下的 `text.md`、`report.md`、`cache/`、`molecules/`、`reports/`。
   - 删除 `index/summaries/<doc_id>.json`。
   - 若 `keep_source = true`：保留 `source.pdf` 和 `.mbforge/index.json`。
   - 若 `keep_source = false`：删除整个 `projects/<doc_id>/` 目录。

5. **错误处理**
   - 使用 `log::error!` 记录每一步失败。
   - 继续尝试清理其他位置，最后汇总为 `Result<(), String>`。

### 3.2 新增 Tauri 命令

#### `project_delete_document(project_root, doc_id)`

- 调用 `cleanup_document_data(doc_id, keep_source=false)`。
- 从 `ProjectIndex` 移除该 `DocumentEntry`。
- 删除 `projects/<doc_id>/` 目录（若清理未删除）。
- 返回 `Result<(), String>`。

#### `project_reingest_document(project_root, doc_id)`

- 调用 `cleanup_document_data(doc_id, keep_source=true)`。
- 重置 `DocumentProject` 的以下状态为初始值：
  - `inspector_status = pending`
  - `text_status = not_processed`
  - `ocr_status = not_processed`
  - `moldet_status = not_processed`
  - `index_status = not_processed`
- 调用 `ingest_enqueue(project_root, source_path, doc_id, force=true)`。
- 返回 `Result<(), String>`。

### 3.3 命令注册

在 `src-tauri/src/commands/mod.rs` 的 `generate_handler!` 中注册：

```rust
project_delete_document,
project_reingest_document,
```

---

## 4. 前端设计

### 4.1 入口位置

文件：`frontend/src/components/project/DocumentList.tsx`

在每行右侧添加两个行内图标按钮：

- 重新读取：↻ 图标（tooltip："重新读取"）
- 删除：🗑 图标（红色，tooltip："删除"）

按钮在文档处理中或入队时禁用，避免冲突。

### 4.2 交互流程

**删除：**

1. 用户点击 🗑。
2. 调用 `@tauri-apps/plugin-dialog` 的 `ask()`，文案：
   - zh-CN：`将永久删除 {filename} 及其所有分子、向量和笔记，是否继续？`
   - en：`Permanently delete {filename} and all associated molecules, vectors, and notes?`
3. 用户确认后，按钮进入 loading 状态。
4. 调用 `deleteDocument(projectRoot, docId)`。
5. 成功后 toast 提示，调用 `onRefreshDocs()` 刷新列表。

**重新读取：**

1. 用户点击 ↻。
2. 调用 `ask()`，文案：
   - zh-CN：`将清空 {filename} 的所有抽取结果并重新读取，是否继续？`
   - en：`Clear all extracted results for {filename} and re-ingest?`
3. 用户确认后，按钮进入 loading 状态。
4. 调用 `reingestDocument(projectRoot, docId)`。
5. 成功后 toast 提示，调用 `onRefreshDocs()` 刷新列表。

### 4.3 API 封装

在 `frontend/src/api/tauri/project.ts` 新增：

```typescript
export async function deleteDocument(projectRoot: string, docId: string): Promise<void> {
  return invoke('project_delete_document', { projectRoot, docId })
}

export async function reingestDocument(projectRoot: string, docId: string): Promise<void> {
  return invoke('project_reingest_document', { projectRoot, docId })
}
```

### 4.4 i18n 键

在 `frontend/src/i18n/locales/en.json` 和 `zh-CN.json` 中新增：

```json
{
  "doc": {
    "reingest": "重新读取",
    "delete": "删除",
    "reingestConfirm": "将清空 {filename} 的所有抽取结果并重新读取，是否继续？",
    "deleteConfirm": "将永久删除 {filename} 及其所有分子、向量和笔记，是否继续？",
    "reingestSuccess": "已重新读取 {filename}",
    "deleteSuccess": "已删除 {filename}",
    "reingestError": "重新读取失败：{error}",
    "deleteError": "删除失败：{error}"
  }
}
```

---

## 5. 数据流

```
用户点击删除/重读
   ↓
二次确认对话框
   ↓
调用 project_delete_document 或 project_reingest_document
   ↓
cleanup_document_data(doc_id, keep_source)
   ├─ 取消运行中任务
   ├─ 清理 molecules.db
   ├─ 清理 knowledge_base.db
   ├─ 清理文件系统（保留或删除 source.pdf）
   └─ 清理 summaries
   ↓
(delete) 从 ProjectIndex 移除 + 删除目录
(reingest) 重置状态 + ingest_enqueue(..., force=true)
   ↓
返回 Result
   ↓
前端刷新列表 + toast
```

---

## 6. 错误处理

- Rust 命令返回 `Result<T, String>`，错误信息包含操作类型和文档 ID。
- 清理过程中单点失败不中断整体流程，记录 `log::error!`，最后汇总返回。
- 删除时若 `source.pdf` 已不存在，视为幂等成功。
- 重新读取时若文档不存在或 source.pdf 缺失，返回可读错误。
- 前端捕获 Tauri invoke 错误，展示 `e.message`。

---

## 7. 测试计划

### Rust 测试

1. **`cleanup_document_data` 残留测试**
   - 构造一个文档，插入分子、关系、检测、向量、coref 标注、摘要。
   - 调用 `cleanup_document_data(doc_id, true)`。
   - 断言：
     - `molecules` / `molecule_images` / `molecule_relations` / `molecule_detections` 无残留
     - `vectors` / `figure_labels` / `coref_predictions` / `file_cache` / `ingest_queue` 无残留
     - `source.pdf` 仍存在，`text.md` / `report.md` / `cache/` 已删除
     - `index/summaries/<doc_id>.json` 已删除

2. **`project_delete_document` 集成测试**
   - 调用命令删除文档。
   - 断言 `ProjectIndex` 中无该文档，`projects/<doc_id>/` 目录不存在。

3. **`project_reingest_document` 集成测试**
   - 调用命令重新读取文档。
   - 断言派生数据已清理，文档状态重置为 pending，ingest queue 中出现新的任务。

### 前端测试

1. **按钮渲染**
   - `DocumentList` 渲染后，每行应出现重新读取和删除按钮。

2. **点击交互**
   - 模拟点击删除按钮，验证调用 `deleteDocument`。
   - 模拟点击重新读取按钮，验证调用 `reingestDocument`。
   - 验证操作成功后调用 `onRefreshDocs`。

---

## 8. 待办/后续扩展

- [ ] 实现 `Project::cleanup_document_data`
- [ ] 实现 `project_delete_document` 命令
- [ ] 实现 `project_reingest_document` 命令
- [ ] 注册命令到 `commands/mod.rs`
- [ ] 前端 `DocumentList` 添加按钮与确认对话框
- [ ] 新增 `deleteDocument` / `reingestDocument` API 封装
- [ ] 添加 i18n 键
- [ ] 补充 Rust 与前端测试
- [ ] 更新 AGENTS.md（若新增约定）

后续可扩展：

- 批量删除/重新读取（方案 C）。
- 软删除与回收站。
- 重新读取时保留用户笔记（可选模式）。

---

## 9. 关键文件清单

```
src-tauri/src/core/project/project.rs
src-tauri/src/core/project/document_project.rs
src-tauri/src/core/document/knowledge_base.rs
src-tauri/src/core/document/ingest_queue.rs
src-tauri/src/core/document/file_cache.rs
src-tauri/src/core/document/detection_cache.rs
src-tauri/src/core/document/summary.rs
src-tauri/src/core/molecule/molecule_db.rs
src-tauri/src/core/molecule/molecule_store.rs
src-tauri/src/commands/mod.rs
src-tauri/src/commands/project_ops.rs 或新增 project.rs
frontend/src/components/project/DocumentList.tsx
frontend/src/components/project/ProjectDashboard.tsx
frontend/src/api/tauri/project.ts
frontend/src/i18n/locales/en.json
frontend/src/i18n/locales/zh-CN.json
```
