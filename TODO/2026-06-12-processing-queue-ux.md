# 处理队列 UX 优化 + 当前 PDF 流程图

> 立项：2026-06-12
> 范围：Phase 1 (A+B) + Phase 2 (C+G)
> 涉及：`ProcessingQueue.tsx` · `PdfViewer.tsx` · `ingest_queue.rs` · `ingest_worker.rs`

## 背景

后端 `ingest_worker.rs` 已发出 5 阶段进度（inspector → text_extract → ocr → moldet → index），但前端：
- `/queue` 全屏页信息密度低、stage 用 emoji 表达、卡片内看不到"走到哪一步"
- `PdfViewer` 完全没订阅 ingest 事件 → 后台处理当前 doc 时 viewer 静默
- 失败任务只能看到一行 error string，缺少上下文

## 方案

### A. PdfPipelineFlow 组件（核心）
- 新建 `frontend/src/components/project/pdf/PdfPipelineFlow.tsx` + `pdf-pipeline-flow.css`
- 5 节点横向流程图，每节点状态：idle / running（脉冲）/ done（打勾）/ failed（红）/ skipped（灰）
- 节点之间连线 + 实时进度 + 当前 stage 详情文本
- 两种尺寸：
  - `compact`（嵌入 `ProcessingQueue` 任务卡，5 个小点 + 当前节点高亮）
  - `full`（`PdfViewer` 顶部 banner，全宽显示含 ETA）
- 实现：纯 React + CSS 变量，零第三方依赖

### B. 队列列表打磨
- `processing-queue.css` 收敛间距、统一对齐
- stage emoji 替换为 `components/icons/science.tsx` 中的 SVG icon
- `IngestTask` 加 `priority: i32`，SQLite schema 同步加列
- 新增 `ingest_set_priority` Tauri 命令 + 前端"置顶"按钮
- done 默认折叠（增强 `hideDone`，不与"全部"过滤冲突）

### C. Worker 吞吐洞察
- `IngestQueue` 加聚合查询：最近 5 个 done 任务的每阶段平均耗时
- `QueueStats` 增加 `avg_stage_durations_ms: [u64; 5]`
- header 增加 1 个 stat chip："近 5 篇 · 平均 1m48s/篇"

### G. 跨页完成 toast
- 顶层 `AppContext` 订阅 `IngestQueueUpdate`
- 当前路由不是 `/queue` 且任务变 `done` 时 `showToast`
- 自己触发的任务不弹（避免噪音）

## 任务拆分

- [ ] **A1** 新建 `PdfPipelineFlow` + 样式
- [ ] **A2** `ProcessingQueue` 每张卡嵌入 compact 版
- [ ] **A3** `PdfViewer` 订阅 ingest 事件，顶部加 full banner
- [ ] **B1** `IngestTask` + SQLite 加 `priority` 列
- [ ] **B2** 新增 `ingest_set_priority` 命令 + 前端"置顶"按钮
- [ ] **B3** stage icon 从 emoji 改 SVG
- [ ] **C1** `IngestQueue` 聚合 `avg_stage_durations_ms`
- [ ] **C2** 前端 header 加吞吐 chip
- [ ] **G1** 跨页完成 toast
- [ ] 编译验证：`cargo check --lib` + `npx tsc --noEmit`
- [ ] 手动验证：50 页 PDF 走完 5 阶段，截图确认 viewer banner + 队列卡同步

## 不做（本轮）

- D. 失败诊断 trace（最近 20 条 progress 事件）→ 下轮
- E. 批量操作 + 暂停 worker 开关 → 下轮
- F. 阶段耗时堆叠条 → 下轮
