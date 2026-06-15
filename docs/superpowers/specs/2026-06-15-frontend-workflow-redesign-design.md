# 前端工作流导航与页面分布重构设计

## 背景与目标

MBForge 前端当前存在以下问题：

1. 页面职责重叠：`/dashboard` 与 `/project` 都显示项目统计与文档列表。
2. 功能入口分散：SAR 分析的后端命令已注册，但前端缺少独立路由入口。
3. 设置入口不统一：`Settings` 是弹窗 Modal，`Environment` 是独立页面，二者内容交叉。
4. 前后端连接不一致：部分后端命令（`molecule_admin`、`chem_ops`）未在前端 API 层完整暴露。
5. 样式文件过大：`global.css` 承载过多功能域样式，难以维护。

本次重构目标是：

- 以用户工作流为核心重新分布页面。
- 消除重复入口，补齐缺失路由。
- 统一前后端命令暴露与错误处理风格。
- 拆分样式文件，优化响应式布局。

## 设计原则

1. 工作流优先：导航按“项目工作台 → 发现 → 分子库 → 分析 → 系统设置”组织。
2. 单一职责：每个页面只承担一个明确工作流域。
3. 最小惊讶：保留用户已熟悉的功能，仅调整入口位置。
4. 渐进可用：优先完成结构迁移，再逐步优化视觉细节。

## 新的信息架构

侧边栏按以下七项工作流入口组织：

| 导航项      | 路由           | 工作流域                     |
|-------------|----------------|------------------------------|
| Workspace   | `/workspace`   | 项目概览、文档浏览、队列摘要 |
| Discover    | `/discover`    | 搜索、对话                   |
| Molecules   | `/molecules`   | 分子库管理                   |
| Analysis    | `/analysis`    | SAR、聚类、活性悬崖          |
| Queue       | `/queue`       | PDF 处理任务中心             |
| Notes       | `/notes`       | 笔记与 Wiki                  |
| Settings    | `/settings`    | 应用配置、环境、资源状态     |

`/` 默认路由重定向到 `/workspace`。

## 页面路由映射与组件调整

### Workspace（合并 Dashboard + Project）

- 路由：`/workspace`（默认页）。
- 职责：项目概览仪表盘 + 文档浏览 + 队列快捷面板 + 最近笔记。
- 默认视图：项目概览仪表盘（统计卡片、最近文档、快捷操作）。
- 组件变更：
  - 新建 `frontend/src/components/workspace/Workspace.tsx`。
  - 新建 `frontend/src/components/workspace/WorkspaceOverview.tsx`。
  - 复用 `frontend/src/components/project/ProjectDashboard.tsx` 中的统计逻辑。
  - 复用 `frontend/src/components/project/ProjectView.tsx` 中的文档浏览逻辑。
  - 将 `SidebarQueuePanel` 的摘要版本嵌入 Workspace 仪表盘。
  - `ProjectScope` 作为 Workspace 页面内的固定左侧文件树面板保留，不再由全局 Sidebar 单独控制。
- 废弃：`/dashboard`、`/project` 路由移除，使用 `/workspace` 替代。

### Discover（合并 Search + Chat）

- 路由：`/discover`。
- 职责：Search 与 Chat 双标签页，共享搜索上下文。
- 组件变更：
  - 新建 `frontend/src/components/discover/Discover.tsx`。
  - 新建 `frontend/src/components/discover/DiscoverTabs.tsx`。
  - 迁移 `frontend/src/components/Search.tsx` → `frontend/src/components/discover/SearchTab.tsx`。
  - 迁移 `frontend/src/components/Chat.tsx` → `frontend/src/components/discover/ChatTab.tsx`。
- 共享上下文：在 Discover 页面级维护当前查询词，Search 结果可作为 Chat 的初始上下文。

### Molecules

- 路由：`/molecules`。
- 职责：分子库 CRUD、子结构搜索、相似性搜索。
- 组件变更：
  - 保留 `frontend/src/components/MoleculeLibrary.tsx` 作为入口。
  - 在 API 层补充暴露 `molecule_admin` 与 `chem_ops` 命令。
  - 新增子视图入口：Admin、Substructure、Similarity、Cluster。

### Analysis（新增）

- 路由：`/analysis`。
- 职责：SAR 分析、R-group 矩阵、聚类、活性悬崖。
- 组件变更：
  - 新建 `frontend/src/components/analysis/Analysis.tsx`。
  - 迁移 `frontend/src/components/SARAnalysis.tsx` → `frontend/src/components/analysis/SarPanel.tsx`。
  - 调用后端命令：`sar_find_scaffold`、`sar_decompose`、`sar_build_matrix`、`sar_heatmap`。

### Queue

- 路由：`/queue`。
- 职责：PDF 处理任务中心。
- 组件变更：
  - 保留 `frontend/src/components/project/ProcessingQueue.tsx` 的核心逻辑。
  - 在 `frontend/src/components/queue/ProcessingQueuePage.tsx` 中创建页面级包装组件，接入路由 `/queue`。

### Notes

- 路由：`/notes`。
- 职责：笔记列表与编辑器。
- 组件变更：保留现有 `frontend/src/components/Notes.tsx`。

### Settings（合并 Environment）

- 路由：`/settings`。
- 职责：应用配置、环境检查、资源/模型状态、缓存管理。
- 组件变更：
  - 将 `frontend/src/components/SettingsModal.tsx` 改造为 `frontend/src/components/settings/SettingsPage.tsx`。
  - 新建标签页组件：General、LLM、Models、System、Cache、About。
  - 将 `frontend/src/components/Environment.tsx` 内容迁移到 `System` 标签页。
  - 调用后端命令：`get_settings`、`save_settings`、`sidecar_status`、`environment_check`、`resources_status`、`resources_catalog`。

## 前后端连接修复

### 命令暴露一致性

| 后端模块         | 已注册命令数 | 前端暴露情况 | 修复动作                          |
|------------------|--------------|--------------|-----------------------------------|
| `molecule_admin` | 12           | 未完整暴露   | 在 `molecule.ts` 中补充全部命令   |
| `chem_ops`       | 13           | 少量暴露     | 在 `chem.ts` 中补充全部命令       |
| `sar`            | 4            | 无路由       | 新建 `sar.ts` API 模块            |
| `resources_*`    | 7            | 部分暴露     | 统一在 `environment.ts` 中整理    |

### 统一返回类型

所有前端 API 函数统一返回：

```typescript
interface ApiResult<T> {
  success: boolean
  data?: T
  error?: string
  errorCode?: string
}
```

后端命令保持 `Result<T, String>`，前端 wrapper 负责转换为 `ApiResult<T>`。

### 错误处理

- 所有 API 调用使用 `try/catch`。
- 错误信息通过 `showToast` 展示。
- 页面级组件使用 `ErrorBoundary` 包裹。

## 样式与响应式

### 样式文件拆分

将 `frontend/src/styles/global.css` 按功能域拆分：

- `base.css`：重置、字体、基础元素。
- `theme.css`：CSS 变量、深色/浅色主题。
- `workspace.css`：Workspace 与仪表盘样式。
- `discover.css`：Search/Chat 标签与结果样式。
- `analysis.css`：SAR 与分析视图样式。
- `settings.css`：设置页面布局与表单样式。
- `layout.css`：Sidebar、Header、主布局网格。

### 响应式策略

- Desktop：完整侧边栏 + 可选 ProjectScope/QueuePanel。
- Tablet：侧边栏折叠为 icon-only，ProjectScope 自动收起。
- Mobile：侧边栏变为底部 Tab Bar，Workspace 仪表盘改为单列卡片。

### Sidebar 分组

按工作流分组，用细线分隔：

```
Workspace
Discover
Molecules
Analysis
---
Queue
Notes
---
Settings
```

## 错误处理与加载状态

1. 路由懒加载保持 `Suspense` + `RouteFallback`。
2. 每个工作区页面独立处理数据加载错误，展示 `ErrorBoundary` 回退 UI。
3. API 层统一包装，调用方只需检查 `success`。
4. Settings 页面保存配置时显示加载状态和成功/失败提示。

## 测试策略

1. 类型检查：`cd frontend && npx tsc --noEmit` 必须零错误。
2. 路由测试：验证 `/` 重定向到 `/workspace`，`/dashboard` 和 `/project` 不再存在。
3. API 测试：补充 `molecule_admin`、`chem_ops`、`sar` 命令的单元测试。
4. 组件测试：为 Workspace 仪表盘和 Discover 标签页编写基础渲染测试。
5. 响应式测试：在常见视口宽度下手动验证布局。

## 风险与后续

1. **路由变更影响 deep link**：用户收藏的 `/project` 或 `/dashboard` 链接将失效，需添加重定向或友好提示。
2. **Settings Modal 改为页面**：原先从任意位置打开 Settings 的入口需要改为导航到 `/settings`。
3. **Chat/Search 共享上下文**：需要谨慎设计上下文传递，避免互相干扰。
4. **样式拆分期间可能产生回归**：建议按页面逐步迁移，而不是一次性全量替换。

## 实施优先级

1. P0：完成 Workspace 合并与路由调整。
2. P0：补齐 Analysis 路由与 SAR API 暴露。
3. P1：改造 Settings 为页面并合并 Environment。
4. P1：统一 API 返回类型与错误处理。
5. P2：Discover 双标签与共享上下文。
6. P2：样式文件拆分与响应式优化。
