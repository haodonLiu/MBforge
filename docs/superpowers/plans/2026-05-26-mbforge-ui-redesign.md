# MBForge UI 全面优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对 MBForge PyQt6 桌面应用进行全面 UI 优化，涵盖视觉（暖白/棕配色）、交互（点击反馈、加载状态）、架构（统一组件、主题系统）三个维度。

**Architecture:** 以 `theme.py` 的 `LIGHT_PALETTE`/`DARK_PALETTE` 为单一配色来源，所有组件通过 `ThemeManager.instance().palette()` 获取颜色，保证 light/dark 模式自动同步。工厂函数集中管理，减少分散的硬编码颜色值。

**Tech Stack:** PyQt6, QSS, QPropertyAnimation, QGraphicsOpacityEffect

---

## 文件结构映射

| 文件 | 职责 |
|---|---|
| `src/mbforge/ui/theme.py` | 配色常量、工厂函数、CardWidget、SearchBox |
| `src/mbforge/ui/components.py` | BaseButton、IconButton、EmptyStateWidget、LoadingSpinner、InfoRow、SectionHeader、StatusBadge、ProgressBar、ToolBar |
| `src/mbforge/ui/main_window.py` | 主窗口布局 |
| `src/mbforge/ui/dialogs/dialogs.py` | 通用对话框 |
| `src/mbforge/ui/dialogs/unidock_dialog.py` | UniDock 配置对话框 |
| `src/mbforge/ui/pdf_viewer/viewer.py` | PDF 查看器 |
| `src/mbforge/ui/pdf_viewer/highlight_toolbar.py` | 高亮工具栏 |
| `src/mbforge/ui/pdf_viewer/detection_popup.py` | 检测结果弹出框 |
| `src/mbforge/ui/panels/welcome.py` | 欢迎面板 |
| `src/mbforge/ui/panels/pdf_library.py` | PDF 库面板 |
| `src/mbforge/ui/panels/status_dashboard.py` | 状态仪表板 |
| `src/mbforge/ui/panels/status_indicator.py` | 服务状态指示器 |
| `src/mbforge/ui/panels/todo.py` | Todo 面板 |
| `src/mbforge/ui/panels/mol.py` | 分子面板 |
| `src/mbforge/ui/panels/kb.py` | 知识库面板 |
| `src/mbforge/ui/panels/workflow.py` | 工作流面板 |

---

## Batch 1: 配色系统 & 主题基础

### Task 1: 替换 theme.py 的 LIGHT_PALETTE 为暖白/棕 色系

**Files:**
- Modify: `src/mbforge/ui/theme.py:24-39`

- [ ] **Step 1: 替换 LIGHT_PALETTE**

找到第 24-39 行，将整个 `LIGHT_PALETTE` 字典替换为：

```python
LIGHT_PALETTE = {
    "brand_primary": "#8B6F47",
    "brand_primary_light": "#A8895F",
    "brand_primary_deep": "#6B5433",
    "accent_amber": "#C49A3C",
    "accent_coral": "#C26B4A",
    "success": "#5C8A6A",
    "bg_base": "#FAFAF8",
    "bg_card": "#FFFFFF",
    "bg_hover": "#F5F0EB",
    "bg_zebra": "#F7F4F0",
    "text_primary": "#2D2319",
    "text_secondary": "#7A6A5A",
    "border": "#E0D8CF",
    "border_focus": "#8B6F47",
}
```

- [ ] **Step 2: 替换 DARK_PALETTE**

找到第 42-57 行，将整个 `DARK_PALETTE` 字典替换为：

```python
DARK_PALETTE = {
    "brand_primary": "#C4A070",
    "brand_primary_light": "#D4B080",
    "brand_primary_deep": "#A08050",
    "accent_amber": "#D4AA50",
    "accent_coral": "#D48060",
    "success": "#7AAA8A",
    "bg_base": "#1A1714",
    "bg_card": "#242019",
    "bg_hover": "#2E2820",
    "bg_zebra": "#1F1B17",
    "text_primary": "#E8E0D5",
    "text_secondary": "#9A8A7A",
    "border": "#3A3228",
    "border_focus": "#C4A070",
}
```

- [ ] **Step 3: 更新 _build_button_styles 阴影色**

找到 `_build_button_styles` 函数（第 78-113 行），在 `primary`/`default`/`danger` 三个 QSS 字符串中，均使用当前 palette 的 `brand_primary_deep` 作为 pressed 背景色，不使用硬编码颜色。

将 danger 的 `QPushButton:hover { background: #d4563e; }` 改为：
```python
QPushButton:hover {{ background: {p['accent_coral']}; }}
QPushButton:pressed {{ background: {p['accent_coral']}; }}
```

- [ ] **Step 4: 更新 _build_dialog_qss 的按钮样式**

找到 `_build_dialog_qss`（第 146-188 行），将底部 `QPushButton` 样式加上 hover 和 pressed 状态：

在 `QPushButton:hover` 后添加：
```
QPushButton:pressed {{ background: {p['border']}; }}
```

- [ ] **Step 5: 提交**

```bash
git add src/mbforge/ui/theme.py
git commit -m "refactor(theme): replace palette with warm white/brown tones"
```

---

### Task 2: 修复 components.py 中 bg_secondary 缺失问题并完善组件样式

**Files:**
- Modify: `src/mbforge/ui/components.py`

**问题:** `ToolBar` 第 235 行引用 `p['bg_secondary']`，但 palette 中没有此 key，会导致 KeyError 或空值。需要定义或替换为正确 key。

- [ ] **Step 1: 确认 ToolBar 引用的 bg_secondary**

在 `theme.py` 的 `LIGHT_PALETTE` 和 `DARK_PALETTE` 中均添加 `"bg_secondary": "#EDEAE5"`（Light）和 `"bg_secondary": "#2A2520"`（Dark），表示次级背景色。

在 `LIGHT_PALETTE` 字典末尾添加：
```python
    "bg_secondary": "#EDEAE5",
```
在 `DARK_PALETTE` 字典末尾添加：
```python
    "bg_secondary": "#2A2520",
```

- [ ] **Step 2: 更新 CardWidget 添加阴影**

找到 `CardWidget` 类（约第 411-450 行），将 `__init__` 中的 QSS 替换，加入浅阴影：

```python
        self.setStyleSheet(f"""
        QFrame {{
            background: {p['bg_card']};
            border: 1px solid {p['border']};
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(45,35,25,0.08);
        }}
        """)
```

- [ ] **Step 3: 更新 EmptyStateWidget 移除 emoji 依赖，增强引导性**

找到 `EmptyStateWidget` 类（约第 143-172 行）。将 `icon_label` 的 `font-size: 48px` 改为 `font-size: 36px`，并设置 `color: {p['text_secondary']}`，同时在 `icon` 为空时不显示占位区域（条件判断 `if icon`）。

修改后的 `__init__` 中 icon 部分：
```python
        if icon:
            icon_label = QLabel(icon, parent)
            icon_label.setStyleSheet(f"font-size: 36px; color: {p['text_secondary']};")
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(icon_label)
```

- [ ] **Step 4: 提交**

```bash
git add src/mbforge/ui/theme.py src/mbforge/ui/components.py
git commit -m "fix(theme): add missing bg_secondary key, add shadow to CardWidget, enhance EmptyStateWidget"
```

---

## Batch 2: 主窗口重构

### Task 3: 主窗口布局与面板卡片化

**Files:**
- Modify: `src/mbforge/ui/main_window.py`

- [ ] **Step 1: 审查主窗口布局结构**

读取 `main_window.py` 全文，理解当前 QSplitter 布局：左侧边栏（file_tree）、中间标签页（center_tabs）、底部状态栏。记录各区域的 `setContentsMargins`、`setSpacing` 等布局参数。

- [ ] **Step 2: 更新侧边栏分割线样式**

在主窗口样式相关代码处（如有内联 QSS），将边框改为 `border: 1px solid {p['border']}`，不使用厚重边框或背景色块分割。

- [ ] **Step 3: 检查并更新状态栏样式**

确认 `self.statusbar` 的样式使用了 `ThemeManager` 的 `text_secondary` 色。如果状态栏通过 `setStyleSheet` 硬编码颜色，改为从 `ThemeManager.instance().palette()` 读取。

- [ ] **Step 4: 提交**

```bash
git add src/mbforge/ui/main_window.py
git commit -m "refactor(main_window): apply warm palette to statusbar and splitter"
```

---

### Task 4: 主窗口工具栏与面板卡片化

**Files:**
- Modify: `src/mbforge/ui/main_window.py`

- [ ] **Step 1: 找到文件树和面板创建位置**

在 `main_window.py` 中找到创建 `FileTreeWidget`、`PDFLibraryWidget` 等面板的位置。

- [ ] **Step 2: 将面板包装为 CardWidget**

找到 `self.file_tree` 创建处，将其包裹在 `CardWidget` 中：

```python
from .components import CardWidget

# 找到类似这样的代码:
# self.file_tree = FileTreeWidget(...)
# 替换为:
card = CardWidget(title="文件", parent=self)
file_tree_widget = FileTreeWidget(...)
card.set_content(file_tree_widget)
self.file_tree = card
```

对所有主要面板（PDFLibraryWidget、KBWidget 等）执行同样操作。

- [ ] **Step 3: 提交**

```bash
git add src/mbforge/ui/main_window.py
git commit -m "refactor(main_window): wrap panels in CardWidget for consistent styling"
```

---

## Batch 3: 对话框统一

### Task 5: dialogs.py BaseButton 迁移与样式统一

**Files:**
- Modify: `src/mbforge/ui/dialogs/dialogs.py`

- [ ] **Step 1: 确认所有 QPushButton 已替换为 BaseButton**

搜索 `dialogs.py` 确认所有 `QPushButton(` 已替换为 `BaseButton(`，仅有 `from ..components import BaseButton` 导入存在。

- [ ] **Step 2: 统一对话框圆角**

找到对话框 QSS 应用处（如 `ThemeManager.apply_dialog` 调用）。圆角已在 `_build_dialog_qss` 中设为 8px（输入框）和 6px（按钮），符合 spec 中的 12px 对话框规范。

更新 `_build_dialog_qss` 中的 `QDialog` 样式：
```python
def _build_dialog_qss() -> str:
    p = _p()
    return f"""
    QDialog {{ background: {p['bg_card']}; border-radius: 12px; }}
    ...
    """
```

- [ ] **Step 3: 提交**

```bash
git add src/mbforge/ui/dialogs/dialogs.py
git commit -m "refactor(dialogs): unify dialog styling with warm palette"
```

---

### Task 6: unidock_dialog.py BaseButton 迁移

**Files:**
- Modify: `src/mbforge/ui/dialogs/unidock_dialog.py`

- [ ] **Step 1: 确认所有 QPushButton 已替换为 BaseButton**

搜索文件确认无残留 `QPushButton(` 调用。

- [ ] **Step 2: 应用对话框统一样式**

确保 `ThemeManager.apply_dialog(self)` 在 `__init__` 中被调用。

- [ ] **Step 3: 提交**

```bash
git add src/mbforge/ui/dialogs/unidock_dialog.py
git commit -m "refactor(unidock_dialog): migrate to BaseButton"
```

---

## Batch 4: PDF 查看器 & 高亮工具栏

### Task 7: PDF 查看器工具栏视觉优化

**Files:**
- Modify: `src/mbforge/ui/pdf_viewer/viewer.py`

- [ ] **Step 1: 读取 viewer.py 中的工具栏代码**

找到工具栏创建处（约第 99-173 行），理解当前 `QHBoxLayout` 分组结构。

- [ ] **Step 2: 更新工具栏背景色**

将工具栏 `QHBoxLayout` 外层 widget 的 QSS 从硬编码颜色改为 `bg_hover`：

在工具栏 QWidget 的 `setStyleSheet` 处（当前可能无样式），添加：
```python
p = ThemeManager.instance().palette()
toolbar_widget.setStyleSheet(f"background: {p['bg_hover']}; border-bottom: 1px solid {p['border']};")
```

如果已有 QSS，找到并替换硬编码颜色。

- [ ] **Step 3: 确认所有按钮为 BaseButton**

搜索 `BaseButton(` 确认工具栏按钮（mode、prev、next、zoom、detect、clear）全部为 `BaseButton` 实例。

- [ ] **Step 4: 提交**

```bash
git add src/mbforge/ui/pdf_viewer/viewer.py
git commit -m "refactor(viewer): apply warm palette to toolbar, ensure BaseButton usage"
```

---

### Task 8: 高亮工具栏颜色按钮圆形化

**Files:**
- Modify: `src/mbforge/ui/pdf_viewer/highlight_toolbar.py`

- [ ] **Step 1: 读取 highlight_toolbar.py**

找到颜色选择按钮的 QSS 定义。

- [ ] **Step 2: 将颜色按钮改为圆形色块**

找到颜色预设按钮（约第 34 行 `btn = QPushButton(name)`），将其 QSS 改为圆形色块：

```python
btn.setStyleSheet(f"""
    QPushButton {{
        background: rgb({r*255:.0f},{g*255:.0f},{b*255:.0f});
        border: 2px solid transparent;
        border-radius: 12px;
        padding: 0px;
        min-width: 24px;
        max-width: 24px;
        min-height: 24px;
        max-height: 24px;
    }}
    QPushButton:hover {{
        border: 2px solid {p['border_focus']};
    }}
    QPushButton:selected {{
        border: 2px solid {p['text_primary']};
    }}
""")
```

`p` 为 `ThemeManager.instance().palette()`，`r,g,b` 为预设颜色 tuple。

- [ ] **Step 3: 确认背景/下划线按钮为 BaseButton**

搜索 `BaseButton(` 确认样式切换按钮使用 `BaseButton`。

- [ ] **Step 4: 提交**

```bash
git add src/mbforge/ui/pdf_viewer/highlight_toolbar.py
git commit -m "refactor(highlight_toolbar): circular color swatches, BaseButton for style toggle"
```

---

### Task 9: 检测弹出框样式优化

**Files:**
- Modify: `src/mbforge/ui/pdf_viewer/detection_popup.py`

- [ ] **Step 1: 读取 detection_popup.py**

理解 `DetectionPopup` 布局：标题、分子信息、置信度、操作按钮。

- [ ] **Step 2: 将 InfoRow 用于分子信息展示**

找到分子信息展示的 `QLabel` 列表（约第 60-80 行），将每个键值对替换为 `InfoRow` 组件：

```python
from ..components import BaseButton, InfoRow

# 将类似这样的代码:
# info_layout.addWidget(QLabel(f"SMILES: {smiles}"))
# 替换为:
info_layout.addWidget(InfoRow("SMILES", smiles))
info_layout.addWidget(InfoRow("名称", name or "N/A"))
```

- [ ] **Step 3: 置信度数字使用 accent_amber 色**

找到置信度标签，将其样式设为 `color: {p['accent_amber']}; font-weight: 600; font-size: 15px;`。

- [ ] **Step 4: 确认所有按钮为 BaseButton**

搜索 `BaseButton(` 确认确认/拒绝/编辑按钮使用 `BaseButton`。

- [ ] **Step 5: 提交**

```bash
git add src/mbforge/ui/pdf_viewer/detection_popup.py
git commit -m "refactor(detection_popup): InfoRow for molecule data, amber accent for confidence"
```

---

## Batch 5: 功能面板统一

### Task 10: panels/welcome.py 欢迎面板优化

**Files:**
- Modify: `src/mbforge/ui/panels/welcome.py`

- [ ] **Step 1: 读取 welcome.py**

找到空状态提示和最近项目列表的 UI 结构。

- [ ] **Step 2: 确认 EmptyStateWidget 使用正确**

找到 `EmptyStateWidget` 创建处（约第 119 行），确认 `icon=""` 已传入（emoji 移除已完成）。

- [ ] **Step 3: 提交**

```bash
git add src/mbforge/ui/panels/welcome.py
git commit -m "refactor(welcome): confirm EmptyStateWidget with warm palette"
```

---

### Task 11: panels/pdf_library.py 文件列表斑马纹

**Files:**
- Modify: `src/mbforge/ui/panels/pdf_library.py`

- [ ] **Step 1: 读取 pdf_library.py**

找到文件列表（QTableWidget 或 QListWidget）的创建和样式。

- [ ] **Step 2: 确认文件列表使用斑马纹**

如果列表使用 `create_table` 工厂函数，斑马纹已在 `create_table` 的 QSS 中通过 `bg_zebra` 实现（`QTableWidget::item:nth-child` 或奇偶行区分）。

如果列表使用自定义 QSS，将背景改为 `p['bg_zebra']` 用于奇数行。

- [ ] **Step 3: 确认图标按钮无 emoji**

搜索文件确认无 emoji 字符。

- [ ] **Step 4: 提交**

```bash
git add src/mbforge/ui/panels/pdf_library.py
git commit -m "refactor(pdf_library): zebra striping via theme palette"
```

---

### Task 12: panels/status_indicator.py 服务状态指示器统一

**Files:**
- Modify: `src/mbforge/ui/panels/status_indicator.py`

- [ ] **Step 1: 读取 status_indicator.py**

找到 `ServiceStatusIndicator` 的 UI 结构和颜色定义。

- [ ] **Step 2: 使用 StatusBadge 替代硬编码颜色**

找到每个状态（LLM/Embedding/知识库等）的指示器样式，如果使用硬编码颜色，改为使用 `StatusBadge` 组件。

- [ ] **Step 3: 提交**

```bash
git add src/mbforge/ui/panels/status_indicator.py
git commit -m "refactor(status_indicator): use StatusBadge for service indicators"
```

---

### Task 13: panels/status_dashboard.py 状态仪表板卡片化

**Files:**
- Modify: `src/mbforge/ui/panels/status_dashboard.py`

- [ ] **Step 1: 读取 status_dashboard.py`

找到仪表板面板的布局。

- [ ] **Step 2: 将各状态卡片包装为 CardWidget**

找到各个状态卡片的创建位置，用 `CardWidget(title="...")` 包装：

```python
from ..components import CardWidget

card = CardWidget(title="LLM 服务", parent=self)
card.set_content(status_widget)
layout.addWidget(card)
```

- [ ] **Step 3: 提交**

```bash
git add src/mbforge/ui/panels/status_dashboard.py
git commit -m "refactor(status_dashboard): card-based layout with CardWidget"
```

---

### Task 14: 其余 panels 统一检查

**Files:**
- Modify: `src/mbforge/ui/panels/todo.py`, `src/mbforge/ui/panels/mol.py`, `src/mbforge/ui/panels/kb.py`, `src/mbforge/ui/panels/workflow.py`

- [ ] **Step 1: 逐个读取并检查**

对每个文件执行以下检查：
1. 搜索 `QPushButton(` 确认已替换为 `BaseButton`
2. 搜索 emoji 确认已移除
3. 检查是否有硬编码颜色值（如 `#0F4C81` 等蓝色旧配色），替换为 `p['...']`
4. 检查空状态是否使用 `EmptyStateWidget`

- [ ] **Step 2: 修复发现的问题**

每个文件发现的问题当场修复。

- [ ] **Step 3: 提交**

```bash
git add src/mbforge/ui/panels/todo.py src/mbforge/ui/panels/mol.py src/mbforge/ui/panels/kb.py src/mbforge/ui/panels/workflow.py
git commit -m "refactor(panels): unify todo/mol/kb/workflow panels with warm palette"
```

---

## 最终验收

### 验收检查命令

```bash
# 1. 确认无 emoji
uv run ruff check src/mbforge/ui/ --select=N

# 2. 确认所有 BaseButton
grep -r "QPushButton(" src/mbforge/ui/ --include="*.py" | grep -v "BaseButton\|from PyQt6\|import QPush"

# 3. 确认无硬编码旧配色
grep -rn "#0F4C81\|#4A90D9\|#3D5A80\|#6BA3D6\|#0A3A62\|#1D3557" src/mbforge/ui/ --include="*.py"

# 4. ruff check 通过
uv run ruff check src/mbforge/ui/

# 5. 单元测试通过
uv run pytest tests/unit/ -v
```

### 验收标准回顾

- [ ] 所有按钮有可见点击反馈（BaseButton）
- [ ] 主窗口在 light/dark 模式下配色协调一致
- [ ] 无任何 emoji 字符出现在 UI 中
- [ ] 加载/空状态有合理引导提示
- [ ] 字体使用系统默认，无外部字体依赖
- [ ] ruff check 通过，无 import 错误
