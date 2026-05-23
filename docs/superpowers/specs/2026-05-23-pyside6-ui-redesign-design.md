# MBForge UI Redesign Specification

## Overview

Redesign the MBForge PyQt6 desktop application with a cohesive "Precision Scientific" aesthetic — professional and trustworthy, avoiding the cluttered look of traditional scientific software. Support both light and dark themes with system-following + manual override.

**Status:** Approved — 2026-05-23

---

## Design Direction

**Aesthetic:** 「精准科学感」+「现代极简」

---

## Layout Structure

```
┌─────────────────────────────────────────────────────────────────┐
│  顶部工具栏（主模块导航，brand_primary_deep，48px）                │
│  [文献库] [分子库] [知识库] [TODO] [工作流]        [窗口控制]   │
├────────┬────────────────────────────────────────┬────────────────┤
│ 左侧   │ 中央内容区                              │ 右侧           │
│ 240px  │ 弹性宽度                                │ 280px          │
│        │ ┌──────────────────────────────────┐ │ ┌────────────┐ │
│ [X2]   │ │ 子级标签页（PDF/欢迎页）          │ │ │ 知识库检索 │ │
│ [out-  │ │ [表格/阅读器/详情]                │ │ ├────────────┤ │
│  put]  │ │                                  │ │ │ AI 助手    │ │
│ [PDF]  │ └──────────────────────────────────┘ │ └────────────┘ │
├────────┴────────────────────────────────────────┴────────────────┤
│ [LLM●] [Embed●] [KB●] [MolDB●]  [CPU: xx%] [Mem: xxG]  [进度] │
└─────────────────────────────────────────────────────────────────┘
```

**层次说明：**
- **顶部工具栏**：主模块切换器（文献库 / 分子库 / 知识库 / TODO / 工作流），固定不可关闭
- **左侧边栏**：项目文件树，展示目录结构，点击 PDF → 中央打开阅读器
- **中央内容区**：「欢迎页」或「子级标签页」（PDF 阅读器、表格等），子级标签可关闭
- **右侧面板**：上下分区，上 = 知识库检索，下 = AI 助手对话
- **状态栏**：左侧服务状态圆点 → CPU/内存监控 → 右侧进度条

**Spacing rules:**
- 模块间大间距：16-24px（用留白，不用分割线）
- 模块内小间距：8-12px
- 内容边缘：距窗口边缘至少 12px

---

## Color System

### Light Mode Palette

| Token | Hex | Usage |
|---|---|---|
| `brand_primary` | `#0F4C81` | 品牌主色 — 导航、激活状态、强调 |
| `brand_primary_light` | `#3D5A80` | 次级品牌、悬停状态 |
| `brand_primary_deep` | `#0A3A62` | 深色变体 — 顶部导航栏 |
| `accent_amber` | `#F4A261` | 活性数据、警告、需要关注的状态 |
| `accent_coral` | `#E76F51` | 危险操作、PDF 文件图标 |
| `success` | `#2A9D8F` | 成功状态、验证通过 |
| `bg_base` | `#F7F9FC` | 窗口背景（冷灰白） |
| `bg_card` | `#FFFFFF` | 卡片/面板背景 |
| `bg_hover` | `#EDF2F7` | 行/项悬停状态 |
| `bg_zebra` | `#F0F4F8` | 表格斑马纹（偶数行） |
| `text_primary` | `#1D3557` | 主文字 |
| `text_secondary` | `#7A8A9C` | 标签、占位符、禁用状态（对比度 ≥ 4.7:1）|
| `border` | `#E9ecef` | 分割线、输入框边框 |
| `border_focus` | `#0F4C81` | 聚焦环 |

### Dark Mode Palette

| Token | Hex | Usage |
|---|---|---|
| `brand_primary` | `#4A90D9` | 亮蓝色（适配深色背景） |
| `brand_primary_light` | `#6BA3D6` | 悬停状态 |
| `brand_primary_deep` | `#1D3557` | 深蓝色（对比区域） |
| `accent_amber` | `#F4A261` | 同浅色 |
| `accent_coral` | `#E76F51` | 同浅色 |
| `success` | `#2A9D8F` | 同浅色 |
| `bg_base` | `#0F1419` | 窗口背景 |
| `bg_card` | `#1A1F26` | 卡片/面板背景 |
| `bg_hover` | `#2A3441` | 行/项悬停状态 |
| `bg_zebra` | `#1A2430` | 表格斑马纹（与 bg_card 区分）|
| `text_primary` | `#E8EDF2` | 主文字 |
| `text_secondary` | `#6B7A8C` | 标签、占位符 |
| `border` | `#2A3441` | 分割线 |
| `border_focus` | `#4A90D9` | 聚焦环 |

---

## Component Style Guide

### 顶部主模块导航（Tab Bar）

- **激活模块**：透明背景 + 底部 2px `brand_primary` 指示条（滑动动画 250ms ease-out）
- **未激活**：`text_secondary`，悬停 → `bg_hover` 背景
- **无关闭按钮**（主模块固定）
- 字体：13px medium

### 中央子级标签页

- 与主模块相同的 Tab Bar 样式
- 可关闭，关闭按钮平时隐藏，悬停时淡入（200ms）
- 字号比主模块略小：12px，与主模块视觉区分
- 位于中央内容区顶部

### 按钮

- **Primary：** `brand_primary` 背景，白色文字，6px 圆角，无边框
  - 悬停：亮度 +10%
  - 点击：缩放至 95%
- **Secondary：** 透明背景，`brand_primary` 文字，1px `brand_primary` 边框
  - 悬停：`brand_primary` 10% 填充
- **Toolbar：** 仅图标，24×24px，悬停显示圆形 `bg_hover` 背景
- **Danger：** `accent_coral` 文字/边框，悬停填充 `accent_coral` 背景

### 输入框与搜索

- **默认：** 仅底部 1px 边框（扁平化）
- **聚焦：** 底部边框 → `brand_primary` + 2px 光晕阴影扩散
- **搜索框：** 胶囊形状（20px 圆角），左侧放大镜图标（`text_secondary`），占位符文字 "搜索..."

### 文件树（左侧边栏）

- 文件夹：线条图标；PDF：`accent_coral`；数据库文件：`success`
- 展开/折叠：`>` chevron + 90° 旋转动画
- 选中项：`bg_hover` 背景 + 左侧 3px `brand_primary` 指示条

### 数据表格

- 表头：12px，中等字重，`text_secondary`，底部 1px 边框线
- 行高：40-44px
- 斑马纹：偶数行 → `bg_zebra`（与 `bg_card` 可见对比）
- 行悬停：`bg_hover` + 左侧 3px 指示条滑入（150ms）
- 选中行：`brand_primary` 10% 透明度背景 + 左侧指示条

### 空状态（双模式）

**模式一：首次使用（从未导入数据）**
- 中央大区域分子线框插画（20% 透明度）
- 标题 + 次要说明 + 主操作按钮

**模式二：过滤无结果（已有数据但筛选后为空）**
- 保留表格框架
- 表头下方中央显示「无匹配结果」+ 次要说明
- 「清除筛选」按钮

### 状态栏服务状态指示器

```
[LLM ●] [Embedding ●] [KB ●] [MolDB ●]  [CPU: xx%] [Mem: xxG]  |  [进度条]
```
- 圆点颜色：`#40c057` 在线 / `#868e96` 离线
- Hover tooltip 显示完整服务状态文本
- 位于状态栏最左侧，永久 widget

---

## Motion & Micro-interactions

| 触发 | 效果 | 时长 |
|---|---|---|
| Tab 切换 | 指示条滑动（非跳跃） | 250ms ease-out |
| 行悬停 | 背景淡入 + 左侧指示条滑入 | 150ms |
| 按钮点击 | 缩放至 95% + 亮度变化 | 100ms |
| 面板展开 | 宽度动画 + 内容透明度渐变 | 300ms |
| 空 → 有数据 | 淡入 + translateY(10px→0) | 400ms |
| 加载中 | 骨架屏 shimmer（非转圈） | 循环 |

---

## Typography

- **中文字体：** 系统默认（PingFang SC / Microsoft YaHei）
- **字重：** 400（正文）、500（标签/表头）、700（标题）
- **字号阶梯：**
  - 窗口标题：16px medium
  - 主模块 Tab：13px medium
  - 子级 Tab：12px regular
  - 正文/表格：13px regular
  - 辅助说明：11px regular，`text_secondary`

---

## Theme Switching Architecture

### 双层系统

1. **系统跟随** — 启动时通过 `QStyleHints.colorScheme()` 读取系统深/浅色偏好
2. **手动覆盖** — 用户可在设置中强制指定浅色/深色，存入 `ProjectSettings`
3. **信号派发** — `ThemeManager` 持有当前调色板，emit `theme_changed` 信号；所有 widget 订阅并更新 QSS

### 实现要点

- `ThemeManager` 成为调色板唯一数据源
- 所有硬编码 hex 值替换为 `ThemeManager.get_color("token_name")` 或直接引用调色板变量
- `SettingsDialog` 添加「主题」选项：[跟随系统 / 浅色 / 深色] 单选按钮

### 文件变更清单

1. `theme.py` — 调色板字典 + light/dark 变体；`ThemeManager.get_color()` + `theme_changed` 信号
2. `components.py` — `StatusBadge`、`InfoRow`、`EmptyStateWidget`、`SectionHeader` 使用 theme
3. `main_window.py` — 首页按钮样式、服务指示器圆点、状态栏
4. `chat_widget.py` — 消息气泡、输入区域
5. `welcome_widget.py` — 卡片背景、最近项目行
6. `kb_panel.py` — 片段列表、详情面板
7. `pdf_library.py` — PDF 列表、详情预览
8. `mol_panel.py` — 表格、结构预览
9. `pdf_viewer.py` — 工具栏、页码导航
10. `file_tree.py` — 条目样式
11. `todo_panel.py` — 列表项、进度
12. `dialogs.py` — 对话框样式

---

## Icon Style

- 风格：线条图标（outline），2px 描边，圆角端点
- 尺寸：工具栏 24px，列表 16px，按钮 20px
- 颜色：`text_secondary` 默认，`brand_primary` 悬停/激活，禁用时 30% 透明度
- 化学相关图标：几何抽象化（六边形 = 苯环，球棍简化）

---

## Implementation Phases

### Phase 1: Foundation（theme.py + ThemeManager）
- 定义 light/dark 调色板字典
- `ThemeManager.get_color(key)` + `theme_changed` 信号
- `colorSchemeChanged` 监听实现系统跟随
- `is_dark_mode()` 辅助方法
- 所有工厂函数迁移至调色板

### Phase 2: Core Components（components.py）
- `StatusBadge`、`InfoRow`、`EmptyStateWidget`、`SectionHeader` 使用新调色板
- `StatusIndicator` 更新圆点颜色

### Phase 3: Main Window + Panels
- `main_window.py`：顶部导航栏样式、主模块 Tab（无关闭按钮）、子级 Tab、首页按钮、状态栏
- `welcome_widget.py`：卡片背景、最近项目行、系统状态
- `chat_widget.py`：消息气泡（Markdown 渲染 HTML 颜色变量）、输入区域
- `kb_panel.py`：片段列表、详情面板
- `pdf_library.py`：PDF 列表、详情预览、空状态双模式
- `mol_panel.py`：表格、分子结构预览
- `pdf_viewer.py`：工具栏、页码导航
- `file_tree.py`：条目样式
- `todo_panel.py`：列表项、进度
- `dialogs.py`：对话框样式

### Phase 4: Settings Integration
- `SettingsDialog` 添加「主题」选项卡
- 持久化覆盖设置到 `ProjectSettings`
- 手动覆盖优先级高于系统跟随

---

## References

- Figma：Tab 交互、空状态处理
- VS Code：侧边栏与主内容区层级关系
- Notion：留白哲学、极简按钮
- ChemDraw：化学专业感（去掉过时渐变）
- Linear：现代 SaaS 深色/浅色平衡、动效细腻度
