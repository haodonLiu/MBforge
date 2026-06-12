# Plan: PDF 作为第一等公民 + ProjectScope + 侧边栏处理队列

## 目标
- 将左侧文件树从「全文件树」改造为只展示**已解析完成**的 PDF 子项目（DocumentProject），并更名为 **ProjectScope**。
- 未解析（`index_status !== 'done'`）的 PDF 不再出现在 ProjectScope 中，而是自动进入**处理队列**。
- 处理队列同时保留完整页面 `/queue`，并在**左侧边栏**新增一个可折叠的 mini 队列面板。

## 已确认的需求边界
1. **"未解析" 定义**：`index_status !== 'done'` 的 PDF 均为未解析。
2. **侧边栏队列形式**：既保留 `/queue` 完整页面，又在 Sidebar 增加 mini 面板。

## 实现步骤

### 1. 后端：自动将未解析 PDF 加入处理队列
- 在 `src-tauri/src/commands/pdf.rs` 新增命令：
  ```rust
  pub async fn enqueue_unresolved_documents(project_root: String) -> Result<Value, String>
  ```
  - 打开项目，遍历 `doc_type == "pdf"` 且 `index_status != "done"` 的文档。
  - 对每个文档调用 `IngestQueue::enqueue_with_stage(path, doc_id, "inspector")`。
  - 利用 `enqueue_with_stage` 已有的 hash 幂等逻辑，避免重复入队。
  - 返回 `{ success: true, enqueued: number }`。
- 在 `src-tauri/src/commands/mod.rs` 的 `handler()` 中注册该命令。

### 2. 前端 API 层
- 在 `frontend/src/api/tauri/project.ts` 新增：
  ```ts
  export async function enqueueUnresolvedDocuments(projectRoot: string): Promise<number>
  ```
- 在 `frontend/src/api/tauri/ingest_queue.ts` 已有类型/函数基础上，准备 Sidebar mini 面板复用。

### 3. 关键流程自动触发入队
- `frontend/src/components/Welcome.tsx` / `frontend/src/App.tsx` 的 `openProject` 成功后调用 `enqueueUnresolvedDocuments`。
- `frontend/src/components/project/ProjectDashboard.tsx` / `ProjectView.tsx` 的扫描完成后调用 `enqueueUnresolvedDocuments`。
- `frontend/src/api/tauri/project.ts` 的 `uploadFiles` 完成后调用 `enqueueUnresolvedDocuments`。
- 这样新导入/扫描到的未解析 PDF 会自动出现在处理队列中。

### 4. 用 ProjectScope 替换 FileTree
- 将 `frontend/src/components/FileTree.tsx` 重命名为 `frontend/src/components/ProjectScope.tsx`（同步更新 `App.tsx` 的 import）。
- 数据源从 `get_file_tree` 改为 `list_project_documents`。
- 过滤逻辑：
  ```ts
  docs.filter(d => d.doc_type === 'pdf' && d.index_status === 'done')
  ```
- 渲染为扁平 PDF 列表，每项显示：
  - 文件名/标题
  - 完成状态小图标
  - 点击后在应用内打开 PDF（`setActiveFile({ path, type: 'pdf' })`）
- 保留「导入文件」按钮（可放面板底部）。
- 监听 `EVT.DocResult` 与 `EVT.IngestQueueUpdate`，文档完成索引后自动刷新列表。

### 5. App.tsx 改造
- 用 `<ProjectScope>` 替换 `<FileTree>`。
- 顶部标题从 `t('nav.fileTree')` 改为 `t('nav.projectScope')`。
- 新增 Sidebar mini 队列面板的显隐状态（如 `queuePanelOpen`）。
- 在移动端/平板场景下，ProjectScope 与 mini 队列面板同样受响应式规则约束。

### 6. Sidebar 改造
- 顶部文件树切换按钮 tooltip 改为 `t('nav.projectScope')`。
- 新增队列图标（或复用现有 `QueueIcon`）：
  - 单击：导航到 `/queue`。
  - 右键/长按 或 额外按钮：展开左侧 mini 队列抽屉。
- 队列图标上显示未完成任务数小红点（基于 `ingestStats`）。

### 7. Sidebar mini 队列面板
- 新建 `frontend/src/components/queue/SidebarQueuePanel.tsx`：
  - 复用 `ingestList` / `ingestStats`。
  - 监听 `EVT.IngestQueueUpdate` 与 `EVT.IngestWorkerHeartbeat`。
  - 仅展示 `pending` / `processing` / `failed` 的任务（过滤掉 `done` / `cancelled` 以保持简洁）。
  - 每项显示：文件名、阶段、进度条、状态。
  - 底部提供「查看全部」按钮，跳转 `/queue`。
- 该面板作为 240px 宽的抽屉，从 Sidebar 右侧滑出，与 ProjectScope 不重叠（同一时间只展开一个，或并排在 56px 侧边栏右侧）。

### 8. i18n
- 更新 `frontend/src/i18n/locales/zh-CN.json` 与 `en.json`：
  - `nav.projectScope`
  - `projectScope.empty`
  - `projectScope.import`
  - `sidebarQueue.title`
  - `sidebarQueue.viewAll`

### 9. 样式
- 新建/补充 `frontend/src/styles/project-scope.css`：
  - ProjectScope 面板 header、列表项、空状态、导入按钮样式。
- 新建/补充 `frontend/src/styles/sidebar-queue.css`：
  - mini 队列抽屉、进度条、状态徽章样式。

### 10. 验证
- `cargo check --lib`
- `cargo test --lib ingest_queue ingest_worker project_ops`
- `npx tsc --noEmit`
- 手动验证：
  1. 导入 PDF → 未解析时不出现在 ProjectScope，出现在 Sidebar mini 队列与 `/queue`。
  2. 处理完成后自动出现在 ProjectScope。
  3. 点击 ProjectScope 项可在应用内打开 PDF。

## 风险与注意点
- **队列满载**：自动入队大量 PDF 时可能触发 `MAX_ACTIVE_QUEUE_SIZE`（100），命令返回成功但部分未入队；可在 UI 提示。
- **状态刷新**：ProjectScope 与 mini 队列都依赖事件刷新，确保监听 `EVT.IngestQueueUpdate`（worker 阶段切换/完成时 emit）。
- **文件重命名**：重命名 `FileTree.tsx` 会改变 git 历史；如想保留历史，可先复制内容到新文件再删除旧文件，但本次建议直接重命名以明确语义。
- **Sidebar 宽度**：mini 队列抽屉在 56px Sidebar 外展开，需确保不遮挡主内容；在平板/移动端可改为全屏抽屉或隐藏。

## 预计改动文件
- 后端
  - `src-tauri/src/commands/pdf.rs`
  - `src-tauri/src/commands/mod.rs`
- 前端
  - `frontend/src/App.tsx`
  - `frontend/src/components/Sidebar.tsx`
  - `frontend/src/components/FileTree.tsx` → `frontend/src/components/ProjectScope.tsx`
  - `frontend/src/components/queue/SidebarQueuePanel.tsx`（新建）
  - `frontend/src/api/tauri/project.ts`
  - `frontend/src/api/tauri/index.ts`（如需要调整 barrel export）
  - `frontend/src/i18n/locales/zh-CN.json`
  - `frontend/src/i18n/locales/en.json`
  - `frontend/src/styles/project-scope.css`（新建）
  - `frontend/src/styles/sidebar-queue.css`（新建）
