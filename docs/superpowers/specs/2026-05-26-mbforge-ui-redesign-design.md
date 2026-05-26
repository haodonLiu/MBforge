# MBForge UI 全面优化设计方案

## 1. 概述

**目标**：对 MBForge PyQt6 桌面应用进行全面 UI 优化，涵盖视觉、交互、架构三个维度。

**风格定位**：专业科研工具 + 现代简洁，白/米白/棕 色系，类似高端学术期刊与现代笔记工具的结合。

**字体**：系统默认（`QApplication.font()`），不加载外部字体依赖。

**实施方式**：分5批次推进，完成一批交付一批。

---

## 2. 配色系统

### Light Palette

| Token | 色值 | 用途 |
|---|---|---|
| `bg_base` | `#FAFAF8` | 窗口底色（暖白） |
| `bg_card` | `#FFFFFF` | 卡片/面板背景 |
| `bg_hover` | `#F5F0EB` | 悬浮/选中背景（米色） |
| `bg_zebra` | `#F7F4F0` | 斑马条纹（淡米） |
| `brand_primary` | `#8B6F47` | 主色调（棕） |
| `brand_primary_light` | `#A8895F` | 悬浮状态 |
| `brand_primary_deep` | `#6B5433` | 按下状态 |
| `accent_amber` | `#C49A3C` | 强调色（金棕） |
| `accent_coral` | `#C26B4A` | 警告/危险色（赤陶） |
| `success` | `#5C8A6A` | 成功（橄榄绿） |
| `text_primary` | `#2D2319` | 主文字（深棕） |
| `text_secondary` | `#7A6A5A` | 次要文字 |
| `border` | `#E0D8CF` | 边框（暖灰） |
| `border_focus` | `#8B6F47` | 聚焦边框 |

### Dark Palette

在 Light 基础上降低明度，保留棕色调，不使用纯黑/纯白：

| Token | 色值 |
|---|---|
| `bg_base` | `#1A1714` |
| `bg_card` | `#242019` |
| `bg_hover` | `#2E2820` |
| `bg_zebra` | `#1F1B17` |
| `brand_primary` | `#C4A070` |
| `brand_primary_light` | `#D4B080` |
| `brand_primary_deep` | `#A08050` |
| `accent_amber` | `#D4AA50` |
| `accent_coral` | `#D48060` |
| `success` | `#7AAA8A` |
| `text_primary` | `#E8E0D5` |
| `text_secondary` | `#9A8A7A` |
| `border` | `#3A3228` |
| `border_focus` | `#C4A070` |

---

## 3. 架构优化

### 主题系统（theme.py）

- 统一 `LIGHT_PALETTE` / `DARK_PALETTE` 暖色系
- `create_button/create_input/create_label/create_table/create_tree` 等工厂函数返回统一组件
- 所有工厂函数默认使用 `BaseButton`（含点击反馈）

### 组件层（components.py）

| 组件 | 现状 | 目标 |
|---|---|---|
| `BaseButton` | 新增，含点击反馈动画 | 完善 |
| `IconButton` | 继承 QPushButton | 改为继承 BaseButton |
| `EmptyStateWidget` | 基础 | 增强引导性，空 icon 区域用插图式占位 |
| `LoadingSpinner` | 文本点动画 | 保留 |
| `InfoRow` | 基础 | 保留 |
| `SectionHeader` | 基础 | 保留 |
| `StatusBadge` | 基础 | 保留 |
| `ProgressBar` | 基础 | 保留 |
| `ToolBar` | 基础 | 保留 |
| `CardWidget` | 基础 | 圆角阴影卡片样式 |

### 按钮点击反馈

已实现：`BaseButton.mousePressEvent` 创建 `QGraphicsOpacityEffect` 透明度 0.65，`mouseReleaseEvent` 启动 120ms `QPropertyAnimation` 恢复。不与 QSS 冲突，不永久占用 effect slot。

---

## 4. 视觉规范

### 圆角半径

| 场景 | 半径 |
|---|---|
| 按钮 | 6px |
| 卡片 | 10px |
| 对话框 | 12px |
| 输入框 | 8px |
| 标签/徽章 | 10px |

### 阴影

卡片组件使用子tle阴影：`0 2px 8px rgba(45,35,25,0.08)`

### 间距系统

- `PADDING_SMALL`: 4px 10px
- `PADDING_DEFAULT`: 6px 12px
- `PADDING_BUTTON`: 6px 16px

### 图标

全部移除 emoji，改用文字或 Qt 内置图标（Qt::StyleHints 返回的系统图标）。

---

## 5. 各模块优化

### 主窗口（main_window.py）

- 侧边栏用 1px `border` 颜色细线分割，不使用厚重边框
- 面板使用圆角卡片承载，带浅阴影
- 顶部工具栏简化，突出核心操作
- 状态栏视觉降噪，使用 `text_secondary` 色

### 对话框（dialogs.py / unidock_dialog.py）

- 统一 12px 圆角
- 表单标签与输入框对齐（QLabel 固定宽度右对齐）
- 按钮组统一在底部右侧
- `BaseButton` 替代所有直接 `QPushButton` 调用

### PDF 查看器（viewer.py）

- 工具栏分组清晰：导航组 | 缩放组 | 标注工具组
- 工具栏背景使用 `bg_hover`，与内容区自然分隔
- 检测分子/清除高亮按钮与颜色选择器视觉分组
- 页码输入框与当前页/总页数标签紧凑排列

### 高亮工具栏（highlight_toolbar.py）

- 颜色选择按钮改为圆形色块，视觉更直观
- 背景/下划线切换按钮使用 `BaseButton` 分组

### 检测弹出框（detection_popup.py）

- 分子信息区域使用 `InfoRow` 统一键值展示
- 操作按钮使用 `primary` / `default` 样式区分主次
- 置信度数值使用 `accent_amber` 色强调

### 面板（panels/*.py）

- `WelcomeWidget`：空状态引导，卡片式布局
- `PDFLibraryWidget`：文件列表使用斑马纹，图标按钮替代 emoji
- `StatusDashboard`：服务状态卡片化，指示器使用 `StatusBadge`
- `TodoPanel`：待办列表紧凑排列，优先级用颜色区分

---

## 6. 交互体验规范

### 加载状态

- 长操作（索引、模型加载）使用 `LoadingSpinner` 覆盖关键区域，不阻塞其他操作
- 进度条显示在操作发生区域的附近（如工具栏右侧），不在弹窗中

### 空状态

每个列表/面板在无数据时显示 `EmptyStateWidget`，包含：
- 简洁文字说明当前状态
- 引导用户下一步的操作按钮（如"索引项目"）

### 错误处理

- 非致命错误（如单文件索引失败）使用内联提示条，不弹窗打断
- 致命错误（模型加载失败等）使用 `QMessageBox.critical`
- 错误文字使用 `accent_coral` 色

### 工具提示（Tooltip）

- 所有按钮带 `setToolTip` 说明功能
- 快捷键在 tooltip 中标注（如 `Ctrl+Z 撤销`）

---

## 7. 实施批次

| 批次 | 内容 | 涉及文件 |
|---|---|---|
| 1 | 配色系统 & 主题基础重构 | `theme.py`, `components.py` |
| 2 | 主窗口重构 | `main_window.py` |
| 3 | 对话框统一 | `dialogs/*.py` |
| 4 | PDF 查看器 & 高亮工具栏 | `viewer.py`, `highlight_toolbar.py`, `detection_popup.py` |
| 5 | 功能面板统一 | `panels/*.py` |

---

## 8. 验收标准

- 所有按钮有可见点击反馈
- 主窗口在 light/dark 模式下配色协调一致
- 无任何 emoji 字符出现在 UI 中
- 加载/空状态有合理引导提示
- 字体使用系统默认，无外部字体依赖
- ruff check 通过，无 import 错误
