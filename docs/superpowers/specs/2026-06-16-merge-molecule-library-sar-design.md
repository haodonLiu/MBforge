# 分子库与 SAR 分析合并设计

**日期**: 2026-06-16  
**主题**: 将 MoleculeLibrary 与 SAR 分析重构为单一视图  
**状态**: 已批准，待实施  

---

## 1. 目标

将当前 MBForge 的分子库（Molecule Library）与 SAR 分析（Structure-Activity Relationship）从"同一页面内的独立 tab"进一步合并为**单一、连贯、数据驱动的分析工作区**：

- 用户在分子列表中选择/过滤化合物时，右侧分析面板实时响应。
- 移除重复的 SAR 容器与独立的 `/analysis` SAR 入口。
- 把当前 `analytics` tab 中的高级分析能力也纳入同一上下文。
- OCR 矫正工作流融入列表过滤与详情编辑，不再作为独立 tab。

---

## 2. 背景

### 2.1 当前实现

| 维度 | 分子库 | SAR 分析 |
|------|--------|----------|
| 入口 | `/molecules`（MoleculeLibrary） | 原独立入口已并入 `/molecules` 的 `sar` tab；`/analysis` 仍有 `SarPanel` |
| 组件 | `frontend/src/components/MoleculeLibrary.tsx` + `frontend/src/components/molecule/*` | `frontend/src/components/SARAnalysis.tsx` + `frontend/src/components/sar/*` |
| 数据 | `MoleculeRecord[]`（`frontend/src/types/index.ts`） | `SARSession`，由 `moleculesToSession()` 从 `MoleculeRecord[]` 派生 |
| API | `api/tauri/molecule.ts`、`molecule_admin.ts` | `api/tauri/sar.ts`，并复用分子库 API 拉取数据 |
| Rust | `commands/molecule.rs`、`commands/molecule_admin.rs`、`core/molecule/*` | `core/chem/sar.rs`、`core/chem/sar_query.rs` |
| 状态 | 独立维护列表、搜索、分页 | 独立维护 session、selectedCompound、correctionItems |

### 2.2 问题

- **重复容器**: `SARAnalysis.tsx` 与 `SarPanel.tsx` 维护几乎相同的状态。
- **上下文割裂**: 用户在 library tab 查看分子，切换到 sar tab 后需要重新加载并转换数据。
- **入口冗余**: `/molecules` 和 `/analysis` 都能进入 SAR，造成导航困惑。
- **Analytics 孤立**: 子结构搜索、聚类、关系、去重等能力与 SAR 分析位于不同 tab，无法基于同一分子集合联动。
- **OCR 矫正隐藏**: 矫正能力 buried 在 SAR tab 内，pending 分子不易被发现。

---

## 3. 设计方案

### 3.1 总体方案

采用 **"左侧可筛选分子列表 + 右侧 Tab 分析面板"** 的单一视图：

- **唯一入口**: `/molecules`。
- **左右分栏**:
  - 左侧：分子表格（默认）/ 卡片网格（可切换），支持多选、排序、分页、过滤。
  - 右侧：分析面板，基于当前选中集合实时计算 SAR 与高级分析结果。
- **详情抽屉**: 单击行/卡片从右侧或底部滑出详情抽屉，支持查看与编辑；OCR 矫正模式下抽屉变为矫正面板。
- **移除冗余**:
  - 删除 `/analysis` 路由中的 `SarPanel`（或重定向到 `/molecules`）。
  - 删除 `SARAnalysis.tsx` 中的重复 session 管理，改为由 `MoleculeLibrary` 统一维护。

### 3.2  rejected 方案

| 方案 | 说明 | 未采纳原因 |
|------|------|------------|
| B 渐进式 | 保留 library/sar/analytics tab，仅在 library tab 内嵌轻量预览 | 未真正合并，tab 嵌套 tab 易混乱 |
| C 可调整分屏 | 右侧为可折叠抽屉，分析工具作为弹窗 | 交互复杂，小屏体验差 |

---

## 4. 页面布局

```
┌─────────────────────────────────────────────────────────────────────┐
│  Molecules                                          [Add] [Import]   │
├──────────────────────────────┬──────────────────────────────────────┤
│                              │                                      │
│  [Table ▼] [Filter ▼] [Sort] │  [Overview] [R-Group] [Cliffs]       │
│  [Search...] [status:all ▼]  │  [Analytics] [Relations]             │
│                              │                                      │
│  ┌────────────────────────┐  │  ┌────────────────────────────────┐  │
│  │ ☑ Name   Activity Type │  │  │ SessionOverview /              │  │
│  │────────────────────────│  │  │ RGroupMatrixView / ...         │  │
│  │ ☑ CMPD-1  245 nM       │  │  │                                │  │
│  │ ☐ CMPD-2  pending      │  │  │                                │  │
│  │ ☑ CMPD-3  12 uM        │  │  │                                │  │
│  └────────────────────────┘  │  └────────────────────────────────┘  │
│                              │                                      │
│  Page 1 / 12   [<<] [<] [>]  │                                      │
│                              │                                      │
└──────────────────────────────┴──────────────────────────────────────┘
```

- 左侧固定最小宽度 360px，最大宽度 50%，默认 40%。
- 右侧分析面板占剩余空间。
- 响应式：小于 1024px 时左侧折叠为顶部搜索条，分析面板独占视图。

---

## 5. 左侧分子列表

### 5.1 视图模式

- **默认表格视图**：列包括 Name、E-SMILES / SMILES、Activity、Activity Type、Units、Status、Source Doc、Source Type。
- **卡片网格视图**：保留现有视觉风格，每卡显示结构缩略图（`MoleculeDisplay`）、名称、活性 badge、状态 badge。
- **视图切换按钮**：保存用户偏好到 `localStorage`，key 为 `mbforge_molecule_view_mode`。

### 5.2 选择

- 支持 **多选**（shift 连选、ctrl 单选、表头全选）。
- 无选中时：右侧分析面板基于**整个项目分子集合**计算。
- 有选中时：右侧基于**选中集合**计算。
- 选中项上限：出于性能考虑，R-group / activity cliffs 等计算限制为最多 200 个分子；超出时提示用户。

### 5.3 过滤

- **文本搜索**: 复用 `mol_admin_search_text`（FTS5）。
- **状态过滤**: `all` / `confirmed` / `pending` / `rejected` / `corrected`。
  - 选择 `pending` 时进入 **OCR 矫正模式**：列表显示 pending 分子，详情抽屉变为矫正面板。
- **来源过滤**: 按 `source_type` 和 `source_doc` 聚合。
- **活性过滤**: 按 activity 范围（最小/最大）过滤。

### 5.4 排序与分页

- 排序字段：Name、Activity、Status、Created At。
- 分页：每页 50 / 100 / 200 可配置。
- 后端分页：使用 `mol_admin_list` 的 limit/offset，避免一次性加载全部分子。

### 5.5 新增/编辑

- "Add" 按钮打开现有 `AddMoleculeDialog`。
- 行/卡片点击打开 **详情抽屉**，复用/改造 `MoleculeDetailPanel` 以支持 `MoleculeRecord` 编辑。
- 批量操作：批量修改 status、批量删除（需二次确认）。

---

## 6. 右侧分析面板

### 6.1 Tab 划分

| Tab | 内容 | 数据来源 |
|-----|------|----------|
| **Overview** | `SessionOverview`：化合物总数、已测活性数、高活性数、最佳化合物、来源文档分布 | 当前集合的 `MoleculeRecord[]` |
| **R-Group** | `RGroupMatrixView`：共同骨架、取代基矩阵、活性热力图 | `sar_build_matrix`、`sar_heatmap` |
| **Activity Cliffs** | `CliffsTab`：相似度高但活性差异大的分子对 + `ScaffoldProfile` | `mol_find_activity_cliffs`、`mol_scaffold_profile` |
| **Analytics** | 原 analytics tab 的 5 个工具：子结构搜索、活性类似物、聚类、关系网络、批量去重 | 复用现有命令 |
| **Relations** | 分子关系图（similar / same_as / scaffold / cluster） | `mol_find_by_molecule`、`mol_get_relation` |

### 6.2 未选中/空状态

- 未选中分子时，默认基于整个项目加载的数据进行分析。
- 当前过滤结果为空时，右侧显示空状态提示，并提供"清除过滤"按钮。

### 6.3 Analytics 工具整合细节

- **子结构搜索**：输入 SMILES/E-SMILES，在当前集合中搜索；结果高亮到列表。
- **活性类似物**：基于当前集合查找 analogs with activity。
- **聚类**：对当前集合运行聚类，支持分配/移除 cluster。
- **关系网络**：展示当前集合内分子间的关系图。
- **批量去重**：对当前集合运行去重，标记/合并重复分子。

---

## 7. OCR 矫正工作流

### 7.1 入口

- 左侧过滤器中增加 **"OCR Correction"** 快速选项，等价于 `status=pending`。
- 选择后列表仅展示 pending 分子，顶部显示矫正模式提示条。

### 7.2 交互

- 点击 pending 行打开详情抽屉，抽屉内显示 `CorrectionPanel`：
  - 左侧：原始检测结果图像（`molecule_detections`）与当前 E-SMILES。
  - 右侧：结构编辑器 / SMILES 输入框、置信度、状态选择（confirmed / corrected / rejected）。
- 支持"保存并下一个"快速流转。
- 矫正结果通过 `mol_store_update_batch` 或 `mol_admin_update` 回写分子库。

### 7.3 状态同步

- 矫正保存后，列表中对应行状态立即更新，不再出现在 pending 过滤中。
- 退出矫正模式后刷新整个列表。

---

## 8. 数据流与状态管理

### 8.1 前端状态

在 `MoleculeLibrary` 中统一维护：

```ts
interface MoleculeLibraryState {
  // 列表状态
  molecules: MoleculeRecord[]
  totalCount: number
  query: string
  filters: {
    status: 'all' | 'confirmed' | 'pending' | 'rejected' | 'corrected'
    sourceType: string | 'all'
    sourceDoc: string | 'all'
    activityMin: number | null
    activityMax: number | null
  }
  sort: { field: string; direction: 'asc' | 'desc' }
  pagination: { page: number; pageSize: number }
  viewMode: 'table' | 'card'

  // 选择与详情
  selectedIds: Set<string>
  detailMolecule: MoleculeRecord | null
  isDetailOpen: boolean
  isCorrectionMode: boolean

  // 分析面板状态
  activeAnalysisTab: 'overview' | 'rgroup' | 'cliffs' | 'analytics' | 'relations'
}
```

### 8.2 派生数据

- `selectedMolecules`：从 `molecules` 和 `selectedIds` 派生。
- `analysisInput`：优先使用 `selectedMolecules`，未选中时使用 `molecules`（当前页/过滤结果）。
- `sarSession`：使用 `moleculesToSession(analysisInput)` 派生，缓存到 `useMemo`，避免重复转换。

### 8.3 API 调用策略

- 列表加载：`mol_admin_list`（分页）。
- 搜索：`mol_admin_search_text`（FTS5）。
- 分析计算：右侧各 tab 自行调用对应命令，但统一从 `analysisInput` 获取输入。
- 防抖：搜索框输入防抖 300ms；分析计算防抖 200ms（多选变化时）。

---

## 9. 后端 / Rust 变化

### 9.1 最小化原则

本次合并以**前端重构为主**，Rust 后端尽量保持不变：

- 复用现有 Tauri 命令：`mol_admin_list`、`mol_admin_search_text`、`mol_admin_update`、`mol_store_update_batch`。
- 复用 SAR 命令：`sar_build_matrix`、`sar_heatmap`、`sar_find_scaffold`、`sar_decompose`。
- 复用分析命令：`mol_search_substructure`、`mol_find_analogs_with_activity`、`mol_assign_cluster`、`mol_list_clusters`、`mol_find_by_molecule`、`mol_add_relation`、`mol_dedup_batch`、`mol_find_activity_cliffs`、`mol_scaffold_profile`。

### 9.2 可能的小幅调整

- 如果 `mol_admin_list` 当前不支持某些过滤字段（如 `activityMin/Max`），可考虑在前端过滤或新增可选参数。
- 如果需要批量获取检测图像信息，可新增 `mol_admin_get_detections(ids)`，避免前端多次调用。

### 9.3 命令注册

- 无需新增命令注册；所有命令已在 `commands/mod.rs` 中注册。

---

## 10. 组件拆分建议

### 10.1 新增组件

| 组件 | 路径 | 职责 |
|------|------|------|
| `MoleculeLibrary` | `frontend/src/components/MoleculeLibrary.tsx` | 重构为单一视图主容器 |
| `MoleculeTable` | `frontend/src/components/molecule/MoleculeTable.tsx` | 表格视图 |
| `MoleculeCardGrid` | `frontend/src/components/molecule/MoleculeCardGrid.tsx` | 卡片网格视图 |
| `MoleculeFilters` | `frontend/src/components/molecule/MoleculeFilters.tsx` | 过滤控件 |
| `MoleculeDetailDrawer` | `frontend/src/components/molecule/MoleculeDetailDrawer.tsx` | 详情/编辑抽屉 |
| `MoleculeAnalysisPanel` | `frontend/src/components/molecule/MoleculeAnalysisPanel.tsx` | 右侧分析面板容器 |
| `useMoleculeLibrary` | `frontend/src/hooks/useMoleculeLibrary.ts` | 列表、选择、过滤状态管理 |
| `useMoleculeAnalysis` | `frontend/src/hooks/useMoleculeAnalysis.ts` | 分析输入派生与 tab 状态 |

### 10.2 复用/改造组件

- `MoleculeDisplay`：复用于表格/卡片缩略图。
- `MoleculeDetailPanel`：改造为支持 `MoleculeRecord` 编辑。
- `CorrectionPanel`：嵌入详情抽屉。
- `SessionOverview`、`OverviewTab`、`RGroupTab`/`RGroupMatrixView`、`CliffsTab`：从 `components/sar/` 迁移到 `components/molecule/analysis/` 或保持原位复用。
- `SubstructureSearchPanel`、`AnalogSearchPanel`、`ClusterPanel`、`RelationPanel`、`DedupPanel`：从 `components/molecule/analytics/` 迁移到右侧 Analytics tab。

### 10.3 删除/废弃

- `frontend/src/components/SARAnalysis.tsx`：功能合并到 `MoleculeLibrary`。
- `frontend/src/components/analysis/SarPanel.tsx`：功能合并到 `MoleculeLibrary`；`/analysis` 路由可移除或改为重定向。
- `frontend/src/components/molecule/MoleculeAnalytics.tsx`：功能合并到右侧 Analytics tab。

---

## 11. 路由与导航

### 11.1 路由变更

| 路由 | 变更 |
|------|------|
| `/molecules` | 唯一分子库与 SAR 入口，渲染重构后的 `MoleculeLibrary` |
| `/analysis` | 移除 SAR 面板；若页面仍存在，默认显示其他分析能力或重定向到 `/molecules` |
| `/molecules?tab=sar` 等 | 旧 query 参数可忽略或重定向到 `/molecules` |

### 11.2 Sidebar

- Sidebar 中的 "Molecules" 菜单保持。
- 若原 "Analysis" 菜单仅用于 SAR，可考虑移除或改为其他全局分析入口。

---

## 12. 错误处理

### 12.1 列表加载错误

- 显示可重试错误提示。
- 不阻塞右侧分析面板；右侧基于已有数据或空集合展示。

### 12.2 分析计算错误

- 各分析 tab 独立捕获错误，显示 tab 内错误状态。
- R-group / cliffs 计算失败时提示用户检查选中集合是否包含有效 SMILES 和活性数据。

### 12.3 矫正保存错误

- 显示具体错误信息，保留用户输入，支持重试。

---

## 13. 性能考虑

- **虚拟滚动**：表格行数超过 200 时启用虚拟滚动（使用现有 `DataTable` 或引入 `react-window`）。
- **分页加载**：避免一次性加载全部分子。
- **分析计算防抖**：多选变化后 200ms 再触发分析计算。
- **Memoization**：`sarSession`、`selectedMolecules`、分析结果使用 `useMemo`。
- **取消请求**：切换 tab 或过滤条件时取消进行中的分析请求（Tauri invoke 不可取消，但至少忽略过期结果）。

---

## 14. 测试策略

### 14.1 前端测试

- 列表渲染：验证表格/卡片切换、分页、排序。
- 选择联动：验证多选后右侧分析输入正确更新。
- 过滤：验证状态过滤、OCR 矫正模式切换。
- 详情抽屉：验证点击行打开、编辑保存。
- 空状态：验证无分子、无选中、过滤为空时的提示。

### 14.2 Rust 测试

- 复用现有测试，确保命令接口不变。
- 若新增批量获取 detections 接口，补充对应单元测试。

### 14.3 集成测试

- 端到端验证：添加分子 → 进入列表 → 选中 → R-group 分析 → OCR 矫正 → 保存 → 状态更新。

---

## 15. 影响范围

| 文件/目录 | 影响 |
|-----------|------|
| `frontend/src/components/MoleculeLibrary.tsx` | 完全重写为单一视图 |
| `frontend/src/components/molecule/*` | 新增/改造多个组件 |
| `frontend/src/components/sar/*` | 复用，可能迁移目录 |
| `frontend/src/components/molecule/analytics/*` | 迁移到右侧 Analytics tab |
| `frontend/src/components/analysis/SarPanel.tsx` | 删除或废弃 |
| `frontend/src/components/SARAnalysis.tsx` | 删除，功能合并 |
| `frontend/src/api/tauri/sar.ts` | 继续复用，无需大改 |
| `frontend/src/App.tsx` | 调整 `/analysis` 路由 |
| `frontend/src/components/Sidebar.tsx` | 可能调整菜单项 |
| `src-tauri/src/*` | 最小改动，复用现有命令 |

---

## 16. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 改动范围大，影响现有用户习惯 | 保留核心交互（添加分子、查看详情、R-group 分析），仅改变布局 |
| 大项目分子数多时性能下降 | 后端分页、前端虚拟滚动、分析计算限制 200 分子 |
| `SARAnalysis` 与 `SarPanel` 状态逻辑复杂 | 统一提升到 `MoleculeLibrary`，子组件仅接收 props |
| 旧 query 参数 `/molecules?tab=sar` 失效 | 添加兼容重定向 |

---

## 17. 验收标准

- [ ] `/molecules` 页面为左右分栏单一视图。
- [ ] 左侧默认表格视图，支持切换卡片网格。
- [ ] 支持多选分子，右侧分析基于选中集合实时刷新。
- [ ] 右侧包含 Overview、R-Group、Activity Cliffs、Analytics、Relations 五个 tab。
- [ ] OCR 矫正通过 `status=pending` 过滤进入，详情抽屉支持矫正编辑。
- [ ] `/analysis` 路由不再包含 SAR 面板（移除或重定向）。
- [ ] 现有 Rust 命令无需破坏性变更即可工作。
- [ ] `npx tsc --noEmit` 零 errors。
- [ ] 核心交互通过手动测试验证。
