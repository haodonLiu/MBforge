# MBForge 前端待办清单

> 本文档汇总前端代码优化和新功能开发中的所有待办事项，按优先级和模块分组。
> 最后更新：2024-12-15

---

## 优先级图例

| 标记 | 含义 |
|------|------|
| [P0] | 阻塞性问题，必须立即处理 |
| [P1] | 高优先级，近期完成 |
| [P2] | 中优先级，纳入下次迭代 |
| [P3] | 低优先级，长期规划 |

---

## 已完成（最近三轮）

- [x] **代码重构与组件抽取**（1166→589 行 SettingsModal）
- [x] **删除冗余组件**：ErrorBanner / SectionHeader / HoverCard / StatusBadge / project/StatCard
- [x] **样式系统化**：tokens.ts（颜色/状态/透明度）、patterns.ts（样式模式/尺寸）
- [x] **图标拆分**：icons/ 目录（nav/actions/ui/science/arrows/brand/）
- [x] **响应式系统**：responsive.ts（5 断点）+ ResponsiveLayout/ShowOn/HideOn/ResponsiveGrid/ResponsiveStatGrid
- [x] **类型导出统一**：ui/types.ts
- [x] **7 个基础组件**：Tabs / Breadcrumb / Pagination / Progress / Steps / AvatarGroup / DataTable / Toast 增强
- [x] **A 页面**：Dashboard 数据看板（折线/柱状/圆环/热力图 + StatCard + 活动流）
- [x] **B 页面**：SAR Analysis（含分子编辑矫正流程）
- [x] **C 页面**：Notes 笔记模块（Markdown + 双链）

---

## A. Dashboard 数据看板 进一步优化

### A.1 交互增强
- [P2] **图表可点击下钻** — 点击折线图某点跳转到该日期的详情面板
- [P2] **数据导出** — 右上角"导出"按钮支持 CSV / PNG
- [P2] **时间范围筛选** — 顶部加 7d/30d/90d/1y 切换器，影响所有图表
- [P3] **图表对比** — 支持选择两个时间段叠加对比

### A.2 真实数据接入
- [P1] **API 适配层** — `src/api/dashboard.ts`，替换 mocks/dashboardMocks.ts
- [P1] **实时刷新** — 用 SSE 或 WebSocket 推送新数据
- [P2] **数据缓存** — SWR 风格的 stale-while-revalidate
- [P2] **空状态优化** — 当无数据时引导用户去索引文献

### A.3 个性化
- [P3] **可配置 Widget** — 允许用户拖拽排序、隐藏某些卡片
- [P3] **主题切换** — Dashboard 卡片密度（紧凑/正常/宽松）
- [P3] **数据导出配置** — 定时生成 PDF 报告邮件订阅

---

## B. SAR Analysis + 分子编辑 进一步优化

### B.1 OCR 矫正流程强化
- [P1] **后端 API 接入** — 把 mock 的 `handleReOCR` 替换为真实调用 `tessera-mol/recognize`
- [P1] **批量保存** — 矫正完成后批量调用 `mol_store_update` 持久化
- [P1] **结构验证** — 用 RDKit 后端做 canonicalize、立体化学校验
- [P2] **差异高亮优化** — 当前是字符级 diff，可改为子结构 diff（SMARTS 比对）
- [P2] **图片裁剪** — CorrectionPanel 接收 sourceImage 时支持放大查看

### B.2 R-Group 矩阵视图（核心功能）
- [P1] **共同骨架识别** — 自动从化合物列表中提取最大公共子结构
- [P1] **R-Group 矩阵表格** — 行=化合物，列=R1/R2/R3/...，显示取代基
- [P2] **活性热力图** — 取代基 × 活性的颜色编码
- [P2] **取代基聚类** — 按结构相似性自动聚类 R-Group
- [P3] **3D 叠合** — WebGL 渲染所有化合物在共同骨架上的叠合

### B.3 SAR 数据管理
- [P2] **导出报告** — CSV / Excel / SDF / PNG（活性-结构图）
- [P2] **筛选** — 按活性范围、来源文献、标签筛选化合物
- [P2] **批量操作** — 多选、批量打标签、批量删除
- [P2] **版本历史** — 化合物结构变更的 git-like 历史
- [P3] **协作注释** — 支持团队成员在化合物上添加评论

### B.4 MoleculeDisplay 增强
- [P2] **2D 编辑器** — 集成 Ketcher 或 JSME 替代 SMILES 文本编辑
- [P2] **3D 预览** — 集成 3Dmol.js 展示 3D 构象
- [P2] **属性计算** — Lipinski 规则、LogP、TPSA 等即时显示
- [P3] **相似分子搜索** — 基于 fingerprint 找类似分子

---

## C. Notes 笔记模块 进一步优化

### C.1 编辑器增强
- [P1] **真正的富文本** — 集成 TipTap 或 Lexical 替代纯 Markdown
- [P1] **代码高亮** — 在 Markdown 中支持 ```python 等语言的语法高亮
- [P2] **数学公式** — 集成 KaTeX（已安装）支持 LaTeX
- [P2] **Mermaid 图表** — 流程图、时序图
- [P2] **图片粘贴上传** — 直接 Ctrl+V 粘贴图片
- [P2] **拖拽排序** — 笔记内章节可通过拖拽排序

### C.2 双链与图谱
- [P1] **真正的双链解析** — 当前是 alert() 提示，需要跳转到对应笔记
- [P1] **反向链接** — 显示"哪些笔记引用了本笔记"
- [P2] **笔记图谱** — 全局双链网络的可视化（d3.js force-directed graph）
- [P2] **未链接引用** — 显示孤儿笔记和未链接的潜在关联
- [P3] **Roam Research 风格块引用** — 引用某段而非整篇

### C.3 笔记组织
- [P2] **文件夹/分层** — 当前只有标签，需要层级结构
- [P2] **全文搜索** — 客户端 fuse.js 索引所有笔记
- [P2] **最近编辑** — 独立面板显示最近修改的笔记
- [P2] **导出** — Markdown / PDF / Notion 格式
- [P2] **导入** — 从 Notion/Obsidian/Roam 导入
- [P3] **笔记模板** — 实验记录 / 会议纪要 / 综述模板
- [P3] **版本历史** — 笔记的 git-like diff

---

## D. 全局改进方向

### D.1 跨页面
- [P2] **命令面板** — Cmd+K 打开，全局搜索 + 快速跳转
- [P2] **主题切换** — 浅色/深色/跟随系统 + 多种 accent color
- [P2] **快捷键系统** — 完整键盘导航（j/k 上下、g+p 项目 等）
- [P2] **通知中心** — 独立的通知页面，分类显示

### D.2 性能
- [P2] **路由级代码分割** — 用 React.lazy() 拆分大页面
- [P2] **虚拟列表** — 大数据集用 react-virtual
- [P2] **图片懒加载** — 分子图片 IntersectionObserver
- [P2] **图表缓存** — 避免重复计算相同数据
- [P3] **PWA / 离线支持** — Service Worker

### D.3 可访问性 (A11y)
- [P2] **键盘导航** — 所有交互元素支持 Tab + Enter
- [P2] **ARIA 标签** — 添加缺失的 aria-label
- [P2] **色盲友好** — 不仅靠颜色传达信息
- [P2] **焦点环** — 键盘焦点可见

### D.4 国际化
- [P2] **i18n 框架** — 接入 react-i18next
- [P2] **中英文切换** — 当前所有硬编码中文字符串
- [P2] **日期/数字格式** — 按 locale 格式化
- [P3] **RTL 支持** — 阿拉伯语等从右到左语言

### D.5 测试
- [P1] **Vitest 配置** — 单元测试框架
- [P2] **核心组件测试** — Button/Card/Tabs 等覆盖 80%+
- [P2] **Hook 测试** — useTheme/useToast/useProjectRoot
- [P2] **页面集成测试** — 主要用户流程
- [P3] **E2E 测试** — Playwright

### D.6 错误处理
- [P2] **ErrorBoundary 增强** — 友好的错误页面 + 重试按钮
- [P2] **离线检测** — 网络断开时显示提示
- [P2] **API 错误规范化** — 统一错误格式 + Toast 提示
- [P2] **日志收集** — 前端错误上报到后端

### D.7 安全
- [P2] **CSP 头** — Content-Security-Policy 防止 XSS
- [P2] **依赖审计** — 定期 `npm audit`
- [P3] **OAuth 集成** — 如果需要多用户系统

---

## E. 现有 UI 组件的进一步打磨

### E.1 已有组件增强
- [P2] **Modal** — 支持嵌套、确认模式（带 danger 按钮）
- [P2] **Toast** — 队列管理、关闭动画优化
- [P2] **Tabs** — 键盘可访问（左右箭头切换）
- [P2] **DataTable** — 列固定（左侧/右侧）、虚拟滚动、行展开
- [P2] **Progress** — indeterminate 状态（不确定进度）
- [P3] **CardGrid** — 拖拽排序

### E.2 缺失组件
- [P2] **Command** — 命令面板（Cmd+K）
- [P2] **Dropdown** — 下拉菜单
- [P2] **Combobox** — 自动补全输入
- [P2] **DatePicker** — 日期选择
- [P2] **RangeSlider** — 范围滑块
- [P3] **ColorPicker** — 颜色选择（设计系统可能需要）
- [P3] **Calendar** — 月历视图
- [P3] **Tree** — 树形结构（FileTree 已有，但应通用化）

### E.3 表单系统
- [P2] **Form 组件** — 统一表单状态管理
- [P2] **Field 包装** — label + 错误信息 + 提示
- [P2] **验证库** — zod + react-hook-form 集成
- [P3] **多步表单向导** — Form Wizard

---

## F. 现有页面改进

### F.1 Chat 对话
- [P2] **消息编辑** — 用户可编辑已发送的消息
- [P2] **分支对话** — 从某条消息分叉出新的对话
- [P2] **语音输入** — Web Speech API
- [P2] **代码块增强** — 复制、运行
- [P2] **消息反馈** — 点赞/点踩 + 反馈说明
- [P3] **导出对话** — Markdown / PDF

### F.2 Search 搜索
- [P2] **高级过滤** — 按文件类型、日期、来源
- [P2] **搜索历史** — 保存最近搜索
- [P2] **保存搜索** — 收藏搜索条件
- [P3] **语义搜索** — 用 embedding 而不是关键词

### F.3 MoleculeLibrary
- [P2] **批量操作** — 选中多个分子做 tag/delete
- [P2] **分子对比** — 选中 2-4 个分子做并排对比
- [P2] **GESim 原子匹配可视化** — 并排渲染两个分子，高亮 GRAAL 对齐的原子对并用连线标注
- [P2] **3D 查看** — 集成 3Dmol.js
- [P2] **导出 SDF** — 一键导出选中的分子
- [P3] **子结构搜索** — 画一个子结构找匹配分子

### F.4 ProjectView 项目看板
- [P2] **项目切换优化** — 切换项目时保留搜索/筛选状态
- [P2] **项目统计可视化** — 添加项目维度的 Dashboard
- [P2] **删除项目** — 带二次确认
- [P3] **项目导出** — 整个项目打包

### F.5 Workflow 工作流
- [P2] **工作流可视化** — 当前是列表，可改为流程图
- [P2] **进度估算** — 预计完成时间
- [P2] **工作流模板** — 内置常见模板

### F.6 Welcome 欢迎页
- [P2] **Onboarding** — 新用户引导流程
- [P2] **最近项目分组** — 按时间分组
- [P2] **快速开始模板** — 一些示例项目

### F.7 SettingsModal
- [P2] **配置导入/导出** — 整个 settings.json
- [P2] **配置版本控制** — Git-like 备份
- [P3] **配置同步** — 跨设备同步

---

## G. 后端对接优先级

### G.1 真实数据替换 mock
- [P1] **dashboardMocks.ts** → `/api/dashboard/*` 端点
- [P1] **sarMocks.ts** → `/api/sar/*` 端点
- [P1] **notesMocks.ts** → `/api/notes/*` 端点
- [P2] **MoleculeLibrary** → 移除 fallback，直接用 Tauri

### G.2 新 API 端点需求
- [P1] **后端支持 R-Group 矩阵计算** — 共同骨架提取
- [P1] **后端支持双链图谱** — 笔记关系查询
- [P1] **后端支持图表数据** — 聚合查询优化
- [P2] **后端支持全文搜索** — 笔记/分子/文献
- [P2] **后端支持活动流** — audit log

---

## H. 工程化

### H.1 工具链
- [P2] **ESLint + Prettier** — 代码规范自动化
- [P2] **Husky + lint-staged** — pre-commit 检查
- [P2] **Conventional Commits** — commit 规范
- [P3] **changesets** — 自动化 changelog

### H.2 构建优化
- [P2] **Bundle 分析** — rollup-plugin-visualizer
- [P2] **代码分割** — React.lazy 拆分大页面
- [P2] **预加载** — 路由级 prefetch
- [P3] **PWA manifest** — 桌面安装

### H.3 CI/CD
- [P2] **GitHub Actions** — PR 检查、构建
- [P2] **自动化部署** — Tauri 打包 CI
- [P3] **版本号自动化** — semantic-release

### H.4 监控
- [P3] **前端监控** — Sentry 错误收集
- [P3] **性能监控** — Web Vitals
- [P3] **用户行为分析** — 匿名埋点

---

## 优先级总结（建议下一轮做）

按 ROI（投入产出比）排序：

1. **[P1] 真实数据接入** — 替换所有 mocks，让前端能真正用起来
2. **[P1] R-Group 矩阵视图** — SAR 分析的核心，竞品都有
3. **[P1] 真正的双链解析** — 笔记模块的核心
4. **[P1] 单元测试配置** — 防止后续回归
5. **[P2] 命令面板 (Cmd+K)** — 大幅提升操作效率
6. **[P2] 主题切换** — 用户体验提升
7. **[P2] Vitest 核心组件测试** — 基础设施
8. **[P2] i18n 框架** — 国际化基础

---

**维护者**：AI Coding Assistant
**状态**：持续更新中
