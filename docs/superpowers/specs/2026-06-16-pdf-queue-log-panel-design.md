# PDF 处理队列详细日志面板设计

**日期**: 2026-06-16  
**主题**: 为 ProcessingQueue 每个任务项添加可展开的处理日志面板  
**状态**: 已批准，待实施  

---

## 1. 目标

为 MBForge 的 PDF 处理队列（`/queue`）增加实时处理日志展示能力：

- 每个队列任务行的末尾添加一个下拉箭头按钮。
- 点击箭头后在当前行下方展开一个日志框，显示该文档实时处理过程中的结构化日志。
- 日志内容包含时间戳、处理阶段、日志级别和消息文本。
- 只展示当前会话中收到的实时日志，不做持久化。

---

## 2. 背景

### 2.1 当前实现

- **队列页面**: `frontend/src/components/project/ProcessingQueue.tsx`
- **后端事件**: `EVT_INGEST_LOG`（`ingest-log`）已在 Rust 端 `ingest_worker.rs` 中发射，包含字段 `doc_id`, `stage`, `level`, `message`, `ts_ms`。
- **前端类型**: `IngestLogEvent` 已在 `frontend/src/api/tauri/ingest_queue.ts` 中定义。
- **当前状态**: 前端订阅了 `EVT_INGEST_PROGRESS`、`EVT_INGEST_QUEUE_UPDATE`、`EVT_INGEST_WORKER_HEARTBEAT` 等事件，但**未消费 `EVT_INGEST_LOG`**。

### 2.2 问题

- 用户只能看到阶段流程图、进度百分比和最终错误信息。
- 处理过程中的详细步骤（如某页 OCR 失败、某个分子检测完成）无法直观查看。
- 已有日志事件基础设施闲置，未在 UI 中暴露。

---

## 3. 设计方案

### 3.1 总体方案

采用 **前端订阅事件 + 每行展开面板** 方案：

- `ProcessingQueue` 组件订阅 `EVT_INGEST_LOG` 事件。
- 使用 `Map<string, IngestLogEvent[]>` 按 `doc_id` 缓存收到的日志。
- 每个任务行末尾渲染一个 `ChevronDown` / `ChevronUp` 切换按钮。
- 点击按钮后，用 `Set<string>` 记录该 `doc_id` 的展开状态。
- 展开时在行下方渲染日志框，过滤并展示该 `doc_id` 的日志。
- 日志框内日志按时间顺序排列，最新日志在底部，并自动滚动到底部。

### 3.2 Rejected 方案

| 方案 | 说明 | 未采纳原因 |
|------|------|------------|
| B 后端缓存 + 命令读取 | Rust 端缓存日志，前端点击时调用命令加载 | 用户选择实时日志即可，避免后端改动 |
| C 全局日志抽屉 | 侧滑抽屉展示所有文档日志 | 用户选择每行展开，更符合按任务排查的直觉 |

---

## 4. UI 设计

### 4.1 任务行

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 📄 patent1.pdf    [inspector] [text] [ocr] [moldet] [index]    ▼  [重试] [取消] │
└─────────────────────────────────────────────────────────────────────────────┘
```

- 在现有操作按钮（重试/取消）左侧添加一个箭头按钮。
- 未展开时显示 `ChevronDown`（▼），展开后显示 `ChevronUp`（▲）。
- `aria-label` 为 "Show logs" / "Hide logs"。

### 4.2 展开后的日志框

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 📄 patent1.pdf    [inspector] [text] [ocr] [moldet] [index]    ▲  [重试] [取消] │
├─────────────────────────────────────────────────────────────────────────────┤
│ 处理日志                                                                       │
│ ─────────────────────────────────────────────────────────────────────────── │
│ 14:32:01  [inspector]  INFO   开始解析 PDF 结构                                 │
│ 14:32:03  [text]       INFO   提取第 1-5 页文本                                 │
│ 14:32:05  [ocr]        WARN   第 3 页 OCR 置信度较低                            │
│ 14:32:08  [moldet]     INFO   检测到 12 个分子图像                              │
│ 14:32:10  [index]      INFO   索引完成                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

- 日志框占满行宽，背景使用 `var(--bg-surface)` 或 `var(--bg-base)`，与行形成层次。
- 边框使用 `var(--border)`，顶部一条分隔线。
- 每条日志一行，字段对齐：
  - 时间：固定宽度，格式 `HH:MM:SS`
  - 阶段 badge：使用与流程图一致的颜色或 `var(--accent-muted)`
  - 级别：颜色编码 — `INFO` 默认、`WARN` 黄色、`ERROR` 红色
  - 消息：自动换行，字体等宽或标准字体
- 空日志时显示："暂无日志，处理开始后将在此显示。"
- 日志条数上限：每个文档最多保留 200 条，超出时丢弃最旧的。

### 4.3 响应式

- 小屏幕下隐藏时间戳，仅保留阶段 + 级别 + 消息。
- 日志框高度最大 240px，超出时内部滚动。

---

## 5. 数据流与状态管理

### 5.1 状态

在 `ProcessingQueue` 组件内维护：

```ts
const [logMap, setLogMap] = useState<Map<string, IngestLogEvent[]>>(new Map())
const [expandedLogDocs, setExpandedLogDocs] = useState<Set<string>>(new Set())
const logBoxRef = useRef<HTMLDivElement | null>(null)
```

### 5.2 事件订阅

```ts
useEffect(() => {
  if (!projectRoot) return
  const unlisten = listen<IngestLogEvent>(EVT.INGEST_LOG, (event) => {
    const { payload } = event
    setLogMap(prev => {
      const next = new Map(prev)
      const list = next.get(payload.doc_id) ?? []
      const updated = [...list, payload]
      if (updated.length > 200) updated.shift()
      next.set(payload.doc_id, updated)
      return next
    })
  })
  return () => { unlisten.then(fn => fn()) }
}, [projectRoot])
```

### 5.3 展开/收起

```ts
const toggleLogs = (docId: string) => {
  setExpandedLogDocs(prev => {
    const next = new Set(prev)
    if (next.has(docId)) next.delete(docId)
    else next.add(docId)
    return next
  })
}
```

### 5.4 自动滚动

- 日志框使用 `useRef` 引用容器。
- 当 `expandedLogDocs` 包含某 `doc_id` 且该文档日志更新时，调用 `scrollTop = scrollHeight`。
- 仅在用户未手动向上滚动时自动滚动（可选优化）。

---

## 6. 组件拆分

### 6.1 新增/改造组件

| 组件 | 路径 | 职责 |
|------|------|------|
| `ProcessingQueue` | `frontend/src/components/project/ProcessingQueue.tsx` | 订阅事件、维护 logMap 和 expandedLogDocs、渲染展开按钮 |
| `IngestLogPanel` | `frontend/src/components/project/IngestLogPanel.tsx` | 接收日志数组，渲染日志列表、空状态、自动滚动 |
| `ChevronDownIcon` / `ChevronUpIcon` | `frontend/src/components/icons/ui.tsx` 或已有 | 箭头图标（若不存在则创建） |

### 6.2 复用类型

- `IngestLogEvent` 来自 `frontend/src/api/tauri/ingest_queue.ts`。
- `EVT` 常量来自 `frontend/src/api/tauri-events.ts`。
- `listen` 来自 `@tauri-apps/api/event`。

---

## 7. 后端变化

### 7.1 最小化原则

本次功能以**前端消费已有事件**为主，Rust 后端**不需要改动**。

### 7.2 已有事件确认

Rust 端已通过 `emit_log()` 发射 `EVT_INGEST_LOG`，前端只需订阅即可。

---

## 8. 错误处理

- 事件监听失败：在组件内捕获并显示轻量错误提示，不影响队列主功能。
- 日志渲染失败：单个日志行渲染异常不应导致整个面板崩溃；使用 Error Boundary 或 try/catch 包裹单行渲染。

---

## 9. 性能考虑

- 每个文档日志上限 200 条，防止内存无限增长。
- 使用 `Map` 和 `Set` 保证 O(1) 查找。
- 日志框使用固定最大高度 + 内部滚动，避免页面过长。
- 仅订阅事件，不频繁调用后端命令。

---

## 10. 测试策略

### 10.1 前端测试

- 测试 `IngestLogPanel` 正确渲染日志列表。
- 测试空日志状态。
- 测试级别颜色渲染。
- 测试 `ProcessingQueue` 中点击箭头展开/收起日志框。

### 10.2 手动测试

- 导入一个 PDF，进入 `/queue`。
- 点击某个任务行的箭头，确认日志框展开。
- 观察处理过程中日志实时追加。
- 切换页面后返回，确认日志已清空（实时日志，不持久化）。

---

## 11. 影响范围

| 文件 | 影响 |
|------|------|
| `frontend/src/components/project/ProcessingQueue.tsx` | 订阅 EVT_INGEST_LOG，渲染展开按钮和日志框 |
| `frontend/src/components/project/IngestLogPanel.tsx` | 新增日志列表组件 |
| `frontend/src/components/icons/ui.tsx` | 可能需要新增 ChevronDown/ChevronUp 图标 |
| `frontend/src/api/tauri/ingest_queue.ts` | 无需修改，复用已有 `IngestLogEvent` |
| `frontend/src/api/tauri-events.ts` | 无需修改，复用已有 `EVT.INGEST_LOG` |
| Rust 后端 | 无需修改 |

---

## 12. 验收标准

- [ ] `/queue` 页面每个任务行末尾出现展开/收起箭头按钮。
- [ ] 点击箭头后在当前行下方显示该文档的处理日志框。
- [ ] 日志框显示时间、阶段、级别、消息。
- [ ] 处理过程中日志实时追加。
- [ ] 日志框最大高度 240px，超出可滚动。
- [ ] 每个文档最多保留 200 条日志。
- [ ] 前端 TypeScript 检查零 errors。
- [ ] 前端测试无回归。
