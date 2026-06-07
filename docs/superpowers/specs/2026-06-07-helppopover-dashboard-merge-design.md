# Design: HelpPopover 自适应 + Sidebar 项目名 Tooltip + Dashboard / Project 合并

**Date**: 2026-06-07
**Status**: Draft (待用户审核)
**Scope**: 前端重构 (frontend/)

---

## 1. 背景与动机

用户在 2026-06-07 提出三件事：

1. **Bug**：Header 右上角「?」点击后，弹出的 `HelpPopover` 经常大半面积跑到窗口外看不见，体感「和 Welcome 页面一样大」。需要让它相对窗口自适应，绝不越出当前可视范围。
2. **合并视图**：当前打开项目后有两个很像的页面 — `/project`（`ProjectView` → `ProjectDashboard`：项目头 + 扫描/索引 + 文件列表）和 `/dashboard`（`Dashboard`：4 张统计卡 + 高活性分子 + 项目概览）。用户希望合并成一个主页。
3. **Tooltip 增强**：Sidebar 每个 nav 标签 hover 时，希望在标签名上方多一行显示当前项目名（类似「workspace 上下文」）。

第三点的项目名在 `AppContext.projectRoot` 里可推导；第一点纯粹是定位 / 尺寸的 bug 修复。

---

## 2. 设计目标

- 单一 `/dashboard` 路由作为打开项目后的主页
- `/project` 路由、`ProjectView.tsx`、`ProjectDashboard.tsx` 删除
- HelpPopover 永不越出视口（4 边越界回弹）
- Sidebar 工具提示显示「项目名 + 标签名」两行
- 不破坏 Welcome（无项目时）、Notes、Search、Chat、Molecules、Environment 等其他页面
- 不动 Rust 后端、FastAPI 端点、Tauri commands
- 不引入新依赖

---

## 3. 架构

### 3.1 路由变更

`frontend/src/App.tsx`：

- 删除 `<Route path="/project" element={...<ProjectView>...}>`
- 删除 `<Route path="/" element={...<ProjectView>...}>` （因为 `/` 也指向 ProjectView）
- 新增/保持 `<Route path="/" element={...<Dashboard>...}>`，`<Route path="/dashboard">` 同样指向 `<Dashboard />`
- `lazy(() => import('./components/ProjectView'))` 删除
- `<AppRoutes>` 其它路由（`/search`、`/chat`、`/molecules`、`/environment`、`/notes`）保持不变

`current` state 不变（仍用 `'dashboard'`）；`AppInner` 里 `setCurrentPage('project')` 调用保持 `'dashboard'`（因为打开项目后应该停在主页）。

### 3.2 文件结构

**新增**（`frontend/src/components/dashboard/`）：

| 文件 | 职责 |
|------|------|
| `StatGrid.tsx` | 6 张统计卡（合并两套 4 卡） |
| `ProjectHeader.tsx` | 项目名 + 路径 + Scan/Index/Settings 按钮 |
| `FolderSpecCard.tsx` | `FOLDER_SPECS` 区块 |
| `FileListPanel.tsx` | 扫描警告 + 索引进度 + 文件列表 |
| `TopMoleculesCard.tsx` | 高活性分子 |
| `ProjectOverviewCard.tsx` | 项目概览 key-value |
| `types.ts` | `IndexProgress` / `DashboardStats` / `ScanWarning` 等类型 |

**修改**：

- `frontend/src/components/Dashboard.tsx` — 重新组装为容器，状态集中
- `frontend/src/components/Sidebar.tsx` — `NavButton` 加 `projectName` prop；Tooltip 支持 ReactNode
- `frontend/src/components/HelpPopover.tsx` — `place()` 加 4 边越界回弹；`useLayoutEffect`
- `frontend/src/components/ui/Tooltip.tsx` — 支持 `content: ReactNode` 替代 `text: string`，向下兼容
- `frontend/src/i18n/locales/en.json` — 删 `nav.project`；`nav.dashboard` 改为「Home」或保留
- `frontend/src/i18n/locales/zh-CN.json` — 删 `nav.project`；`nav.dashboard` 改为「项目主页」

**删除**：

- `frontend/src/components/ProjectView.tsx`
- `frontend/src/components/project/ProjectDashboard.tsx`
- `frontend/src/components/project/` 整个目录（如果空了）
- `frontend/src/components/environment/types.ts` 里 `IndexProgress` 等（如有同名）
- 任何对 `ProjectView` / `ProjectDashboard` 的 import 残留

### 3.3 Sidebar 入口

`NAV_ITEMS` 去掉 `project` 项：

```ts
const NAV_ITEMS = [
  { id: 'dashboard', path: '/dashboard', icon: BarChartIcon, labelKey: 'nav.dashboard' },
  { id: 'notes', path: '/notes', icon: NoteIcon, labelKey: 'nav.notes' },
  { id: 'search', path: '/search', icon: SearchIcon, labelKey: 'nav.search' },
  { id: 'chat', path: '/chat', icon: ChatIcon, labelKey: 'nav.chat' },
  { id: 'molecules', path: '/molecules', icon: FlaskIcon, labelKey: 'nav.molecules' },
  { id: 'environment', path: '/environment', icon: EnvironmentIcon, labelKey: 'nav.environment' },
] as const
```

---

## 4. 组件设计

### 4.1 `Dashboard.tsx`（顶层容器）

Props：

```ts
interface Props {
  onSettingsOpen: () => void
}
```

State：

```ts
const [docs, setDocs] = useState<DocumentEntry[]>([])
const [isLoading, setIsLoading] = useState(false)
const [isIndexing, setIsIndexing] = useState(false)
const [indexProgress, setIndexProgress] = useState<IndexProgress | null>(null)
const [indexResult, setIndexResult] = useState<{ indexed: number; sections: number } | null>(null)
const [error, setError] = useState('')
const [scanWarnings, setScanWarnings] = useState<ScanWarning[]>([])

const [selectedPdf, setSelectedPdf] = useState<DocumentEntry | null>(null)
const [selectedMarkdown, setSelectedMarkdown] = useState<DocumentEntry | null>(null)
const [pdfInitialMode, setPdfInitialMode] = useState<'read' | 'detect' | 'ocr'>('read')

const [stats, setStats] = useState<DashboardStats>({
  documents: 0, indexed: 0, molecules: 0, confirmed: 0,
  conversations: 0, activeThisWeek: 0,
})
const [topMolecules, setTopMolecules] = useState<MoleculeRecord[]>([])
const [refreshing, setRefreshing] = useState(false)
const [statsLoading, setStatsLoading] = useState(true)
```

副作用：

- `useEffect(loadDocs + listen(EVT.DocResult))` — 搬自 `ProjectView`
- `useEffect(loadStats, [projectRoot])` — 搬自 `Dashboard`

行为回调：`handleScan` / `handleIndex` / `handleOpenFile` / `handleCloseFile` / `handleRefresh`。

**文件打开优先**：选中 `selectedPdf` / `selectedMarkdown` 时优先渲染 viewer，否则渲染合并后的主页布局。

### 4.2 `StatGrid.tsx`

```ts
interface Props {
  documents: number
  indexed: number
  molecules: number
  confirmed: number
  sections?: number       // 来自 indexResult，可能为 undefined
  activeThisWeek: number
  conversations: number
}
```

合并自两套 4 卡，统一为 6 张卡（每张都有 `icon`、`label`、`value`、`subValue`、`color`、`variant`）：

| 标签 | 值 | 来源 |
|------|----|------|
| 文献 | `documents` | docs.length |
| 已索引 | `indexed` | docs.filter(d.indexed).length |
| Sections | `sections ?? '—'` | indexResult.sections |
| 分子 | `molecules` | moleculeStatsTauri.total |
| 已确认 | `confirmed` | total - pending |
| 本周操作 | `activeThisWeek` | stats |

使用现有 `<StatCard>` 组件，`<ResponsiveStatGrid>` 包裹。

### 4.3 `ProjectHeader.tsx`

```ts
interface Props {
  projectName: string
  projectRoot: string
  isLoading: boolean
  isIndexing: boolean
  onScan: () => void
  onIndex: () => void
  onSettingsOpen: () => void
}
```

直接搬 `ProjectDashboard` 现有的头区块（IconContainer + PageTitle + 三个 Button）。

### 4.4 `FolderSpecCard.tsx`

无外部 props（直接读 `FOLDER_SPECS`）。直接搬 `ProjectDashboard` 现有的目录规范卡。

### 4.5 `FileListPanel.tsx`

```ts
interface Props {
  docs: DocumentEntry[]
  isLoading: boolean
  isIndexing: boolean
  indexProgress: IndexProgress | null
  indexResult: { indexed: number; sections: number } | null
  error: string
  scanWarnings: ScanWarning[]
  onOpenFile: (doc: DocumentEntry) => void
  onDismissError: () => void
  onDismissWarnings: () => void
}
```

包含：扫描警告 AlertBanner、索引进度条、索引结果提示、文件列表（Skeleton/EmptyState/列表渲染）。

### 4.6 `TopMoleculesCard.tsx`

```ts
interface Props {
  molecules: MoleculeRecord[]
}
```

直接搬 `Dashboard` 现有的高活性分子卡。

### 4.7 `ProjectOverviewCard.tsx`

```ts
interface Props {
  projectRoot: string
  documents: number
  indexed: number
  molecules: number
  confirmed: number
}
```

直接搬 `Dashboard` 现有的项目概览 key-value。

### 4.8 `HelpPopover.tsx` 改动

把 `pos` 状态从 `{ top, right }` 改为 `{ top, left, maxWidth, maxHeight }`：

```ts
interface PopoverPos {
  top: number
  left: number
  maxWidth: number
  maxHeight: number
}

const [pos, setPos] = useState<PopoverPos | null>(null)

const place = () => {
  const a = anchorRef.current
  if (!a) return
  const r = a.getBoundingClientRect()
  const vw = window.innerWidth
  const vh = window.innerHeight
  const MARGIN = 12
  const PANEL_HEADER_RESERVE = 56 // 顶 header 高度 + 一点余量

  const maxWidth = Math.min(440, vw - MARGIN * 2)
  const availableBelow = vh - r.bottom - MARGIN - PANEL_HEADER_RESERVE
  const maxHeight = Math.max(120, Math.min(vh * 0.7, availableBelow))

  // 默认：按钮下方，右对齐（panel 右边 = 按钮右边）
  let top = r.bottom + 6
  let left = r.right - maxWidth

  // 越左：贴左边距
  if (left < MARGIN) left = MARGIN
  // 越右：贴右边距
  if (left + maxWidth > vw - MARGIN) left = vw - MARGIN - maxWidth

  // 越下：翻到按钮上方
  if (top + maxHeight > vh - MARGIN) {
    const aboveTop = r.top - 6 - maxHeight
    if (aboveTop >= MARGIN) {
      top = aboveTop
    } else {
      // 上下都不够：贴顶 + 限高
      top = MARGIN
      const capped = vh - MARGIN - top
      if (capped < maxHeight) {
        // 重新计算 maxHeight 限制
        setPos({ top, left, maxWidth, maxHeight: capped })
        return
      }
    }
  }

  setPos({ top, left, maxWidth, maxHeight })
}
```

`useEffect` → `useLayoutEffect`，事件 listener 维持（resize / scroll / mousedown / keydown）。

### 4.9 `Tooltip.tsx` 改动

扩展 API，向下兼容：

```ts
interface TooltipProps {
  content?: ReactNode   // 新增：可放 JSX
  text?: string         // 旧 API，保留
  children: ReactNode
}
```

实现：`content ?? text` 作为内部渲染。

### 4.10 `Sidebar.tsx` 改动

- `Sidebar` 从 `useAppContext()` 拿 `projectRoot`，`projectName = projectRoot.split('/').pop() || ''`
- `NavButton` 新增 `projectName?: string` prop，传给 Tooltip
- 渲染：`<Tooltip content={<div><div style={{ fontSize: 10, color: 'var(--accent)' }}>{projectName}</div><div>{label}</div></div>}>`

### 4.11 i18n 变更

`en.json`：

```diff
- "nav.project": "Project",
```

`zh-CN.json`：

```diff
- "nav.project": "项目看板",
+ "nav.dashboard": "项目主页",
```

`nav.dashboard` 英文保持 "Dashboard"（"Home" 也可，但 Dashboard 更贴切 — 是数据 + 项目操作的统一主页）。

---

## 5. 数据流

### 5.1 加载时序

```
Dashboard mount (projectRoot 已存在)
  ├─ useEffect: loadDocs()       // listProjectDocuments
  │    └─ listen(EVT.DocResult) // 解析完成刷新
  ├─ useEffect: loadStats()      // listProjectDocuments + moleculeStatsTauri + listMoleculesTauri
  └─ 两者独立，不互相阻塞
```

### 5.2 Scan / Index 流

```
onScan → scanProjectFiles(projectRoot) → setDocs + setScanWarnings
onIndex → scanProjectFiles + listen(EVT.DocProgress) + indexProjectRust
        → setIndexResult + 重新 listProjectDocuments
```

### 5.3 文件打开流

```
FileListPanel.onOpenFile(doc)
  → Dashboard.setSelectedPdf/Markdown
  → 渲染 <PdfViewer doc={...} /> 或 <MarkdownViewer>
  → 关闭时 setSelected*(null) + loadDocs() 刷新
```

### 5.4 Sidebar tooltip 数据

```
useAppContext().projectRoot
  → Sidebar 计算 projectName = projectRoot.split('/').pop() || ''
  → 传 projectName 给每个 NavButton
  → 传入 Tooltip content
```

### 5.5 HelpPopover 位置流

```
mount → useLayoutEffect place()
resize / scroll → place()
open toggle → place()  // 因为尺寸可能变了
```

---

## 6. 错误处理

| 错误源 | 处理 |
|--------|------|
| `listProjectDocuments` 失败 | `setError('Failed to load documents')`，显示 AlertBanner，文件列表 EmptyState |
| `scanProjectFiles` 成功但 `docs.length === 0` 且无 warnings | `setError` 提示用户「请把 PDF 放进 papers/、MD 放进 notes/」 |
| `scanProjectFiles` 抛异常且含 "not allowed" | 显示「扫描文件权限不足」 |
| `moleculeStatsTauri` / `listMoleculesTauri` 失败 | `showToast` warning，`stats` 保持 0，`topMolecules` 为空 |
| `indexProjectRust` 超时（5min） | 显示「索引操作超时」 |
| `indexProjectRust` 含 "ipc.localhost" / "ERR_CONNECTION_REFUSED" | 显示「索引引擎通信失败，请重启应用」 |
| 没有 `projectRoot` | 走 App.tsx 的 Welcome 分支（不变） |
| 文件点开时找不到对应 doc | 走 fallback 路径（已有逻辑），用 `activeFile.path` 构造临时 doc |
| `place()` 在隐藏 anchor 上调用 | `getBoundingClientRect()` 返回 `{top: 0, ...}`，逻辑自然 clamp 到视口内，不会崩溃 |

---

## 7. 边界情况

1. **项目名为空**（`projectRoot === '/'` 或特殊） — `projectName = ''`，Tooltip 不显示第一行
2. **视口宽度 400px**（最小桌面） — HelpPopover `maxWidth = 376px`（400-24），左右各 12px 留白
3. **视口高度 300px**（极小窗口） — HelpPopover 翻到按钮上方仍不够时贴顶 + 限高，`overflowY: 'auto'`
4. **同一时刻多个 nav 标签 hover** — React 事件循环保证单次渲染
5. **ProjectView 文件被其他文件 import**（grep 检查） — 删除前 grep 整个 `frontend/src/`，零引用才删

---

## 8. 测试

### 8.1 手工验收

- `npm run dev`，打开已存在项目
  - 默认进入 /dashboard，显示合并后 6 个区块（Header / StatGrid / FolderSpecCard / TopMolecules+Overview / FileListPanel）
  - 点击 Scan → 看到扫描结果 + warnings
  - 点击 Index → 看到进度条 → 完成后看到结果卡
  - 点击 PDF 行 → 打开 PdfViewer
  - 点击 Refresh → stats 重新加载
- Sidebar hover
  - 每个 nav 按钮 hover，Tooltip 顶部小字显示项目名（`var(--accent)` 颜色）
  - 项目名为空时不显示第一行
- HelpPopover
  - 1200px 视口 → 右对齐靠按钮下方，不超右边
  - 600px 视口 → 占满宽度，左右各 12px
  - 400px 视口 → 高度收缩
  - 300px 视口 → 翻到按钮上方
  - resize 时位置实时更新
  - Esc / 点击外部 / 点击「?」 toggle 关闭

### 8.2 类型检查

- `cd frontend && npx tsc --noEmit` 无错误
- `grep -r "ProjectView\|ProjectDashboard" frontend/src/` 零结果
- `grep -r "nav.project" frontend/src/i18n/` 零结果

### 8.3 回归

- `cd src-tauri && cargo check`（前端改动不影响 Rust，保险）
- 中文 / 英文 i18n 切换显示正确
- 暗色 / 亮色主题切换无样式错乱

---

## 9. 风险与权衡

### 9.1 风险

- **删除 ProjectView 的破坏面**：若有人通过 `import ProjectView` 外部引用，会编译失败 — 通过 grep 8.2 验证
- **StatCard 字段合并**：原 4 卡 + 4 卡 → 6 卡，可能在小屏（1200px 以下）挤 — 用 `ResponsiveStatGrid` 的 `auto-fit, minmax(200px, 1fr)` 自动换行
- **Tooltip 改 API**：所有 `<Tooltip text="...">` 调用要确保 `content` 替代时不影响 — 保留 `text` 作为 fallback

### 9.2 不在范围内

- 不动 Rust 后端
- 不动 FastAPI 端点
- 不动 Tauri commands
- 不改 Welcome（无项目时）— 那是另一回事
- 不改 i18n 其它键
- 不改 HelpPopover 内容（仅改定位 / 尺寸）
- 不重命名 BarChartIcon、ProjectDashboard 等内部 symbol

---

## 10. 实施顺序

1. `Tooltip` 扩展 API（content + text 双支持）— 独立、低风险
2. `Sidebar` 接收 `projectName` + 传 Tooltip content — 独立
3. `HelpPopover` 改定位 — 独立
4. `dashboard/types.ts` — 纯类型
5. `dashboard/ProjectHeader.tsx` — 从 ProjectDashboard 搬
6. `dashboard/FolderSpecCard.tsx` — 从 ProjectDashboard 搬
7. `dashboard/StatGrid.tsx` — 合并两套 4 卡
8. `dashboard/TopMoleculesCard.tsx` — 从 Dashboard 搬
9. `dashboard/ProjectOverviewCard.tsx` — 从 Dashboard 搬
10. `dashboard/FileListPanel.tsx` — 从 ProjectDashboard 搬
11. `Dashboard.tsx` 重写 — 状态集中 + 子组件组合
12. `App.tsx` 删 /project 路由、改 / 指向 Dashboard
13. 删除 `ProjectView.tsx` / `ProjectDashboard.tsx`
14. i18n 删 `nav.project`，改 `nav.dashboard`
15. `cd frontend && npx tsc --noEmit`
16. `cd src-tauri && cargo check`
17. 手工验收 + 截图
18. 提交

---

## 11. 文档同步

- `frontend/src/components/Sidebar.tsx` 顶部注释更新（如有）
- `frontend/src/components/HelpPopover.tsx` 顶部注释更新（说明 4 边回弹）
- 不需要更新 CLAUDE.md / CODEMAP.md（局部重构）
- 不需要更新 CODEMAP.md §7.6 待审核事项（这是普通重构不是 bugfix）

---

## 12. 验收

本 spec 通过以下检查后即可进入 writing-plans 阶段：

- [ ] 用户审核通过本文档
- [ ] 没有 placeholder / TODO
- [ ] 没有内部矛盾
- [ ] 范围聚焦于一个实施计划
- [ ] 没有两可的描述
