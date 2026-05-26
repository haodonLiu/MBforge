# MBForge UI 全面优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对 MBForge PyQt6 桌面应用进行全面 UI 优化：VS Code 风格顶部 Tab 导航，纯黑白灰色系，Light 模式，信息丰富，Obsidian 简约风格。

**Architecture:** 移除左侧边栏和右侧面板，统一为 QTabWidget 顶部 Tab 导航。配色系统全面切换为纯黑白灰色系，Light 模式强制锁定，去除所有棕色/暖色调。所有 UI 组件统一使用 BaseButton（含点击反馈），CardWidget 承载内容区域。

**Tech Stack:** PyQt6, QSS, QGraphicsOpacityEffect + QPropertyAnimation

---

## 配色系统（覆盖 spec 中的暖色系）

用户最终确认方案：
- 纯黑白灰色系，无棕色/暖色
- Light 模式（强制），不切换深色

| Token | Light Value |
|---|---|
| `bg_base` | `#FFFFFF` |
| `bg_surface` | `#F5F5F5` |
| `bg_card` | `#FFFFFF` |
| `bg_hover` | `#EBEBEB` |
| `bg_active` | `#E0E0E0` |
| `border` | `#D0D0D0` |
| `border_focus` | `#000000` |
| `text_primary` | `#1A1A1A` |
| `text_secondary` | `#666666` |
| `accent` | `#000000` |

---

## 文件结构映射

| 文件 | 批次 | 职责 |
|---|---|---|
| `src/mbforge/ui/theme.py` | Batch 1 | 配色常量 + 工厂函数 |
| `src/mbforge/ui/components.py` | Batch 1 | BaseButton + 通用组件 |
| `src/mbforge/ui/main_window.py` | Batch 2 | 顶部 Tab 导航重构 |
| `src/mbforge/ui/dialogs/dialogs.py` | Batch 3 | 对话框统一 |
| `src/mbforge/ui/dialogs/unidock_dialog.py` | Batch 3 | UniDock 对话框 |
| `src/mbforge/ui/pdf_viewer/viewer.py` | Batch 4 | PDF 查看器 |
| `src/mbforge/ui/pdf_viewer/highlight_toolbar.py` | Batch 4 | 高亮工具栏 |
| `src/mbforge/ui/pdf_viewer/detection_popup.py` | Batch 4 | 分子检测弹出框 |
| `src/mbforge/ui/panels/*.py` | Batch 5 | 各功能面板 |

---

## Batch 1: 配色系统 & 主题基础重构

### Task 1: 更新 theme.py 配色为纯黑白灰色系

**Files:**
- Modify: `src/mbforge/ui/theme.py:23-59`

- [ ] **Step 1: 替换 LIGHT_PALETTE**

将 `LIGHT_PALETTE` 整体替换为纯黑白灰色系（删除所有棕色/暖色调）：

```python
LIGHT_PALETTE = {
    "bg_base": "#FFFFFF",
    "bg_surface": "#F5F5F5",
    "bg_card": "#FFFFFF",
    "bg_hover": "#EBEBEB",
    "bg_active": "#E0E0E0",
    "bg_zebra": "#FAFAFA",
    "text_primary": "#1A1A1A",
    "text_secondary": "#666666",
    "border": "#D0D0D0",
    "border_focus": "#000000",
    "accent": "#000000",
    "success": "#4A7A4A",
    "accent_amber": "#666666",
    "accent_coral": "#8A4A4A",
    "bg_secondary": "#F5F5F5",
}
```

- [ ] **Step 2: 替换 DARK_PALETTE**

删除 DARK_PALETTE（Light only 模式不需要），在 `_set_mode` 中强制使用 `LIGHT_PALETTE`：

```python
def _set_mode(self, mode: str) -> None:
    if mode == self._mode:
        return
    self._mode = "light"  # 强制锁定 Light
    self._palette = LIGHT_PALETTE.copy()
    self.theme_changed.emit("light")
```

- [ ] **Step 3: 更新 _build_button_styles 的 primary 样式**

将 `primary` 按钮背景从 `brand_primary` 改为纯黑 `#000000`：

```python
primary = f"""
QPushButton {{
    background: #000000;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: 500;
}}
QPushButton:hover {{ background: #333333; }}
QPushButton:pressed {{ background: #000000; }}
"""
```

- [ ] **Step 4: 更新 _build_global_qss**

将 QMenuBar 背景从 `brand_primary_deep` 改为 `#1A1A1A`：

```python
QMenuBar {{
    background: #1A1A1A;
    color: #ffffff;
    border-bottom: none;
    padding: 0 8px;
}}
```

- [ ] **Step 5: 更新 CardWidget QSS**

CardWidget 背景保持白色，边框使用 `#D0D0D0`：

```python
p = _p()
self.setStyleSheet(f"""
QFrame {{
    background: {p['bg_card']};
    border: 1px solid {p['border']};
    border-radius: 10px;
}}
""")
```

- [ ] **Step 6: 更新 create_table 中的选中色**

QTableWidget::item:selected 背景改为 `#E0E0E0`，文字改为 `#1A1A1A`：

```python
QTableWidget::item:selected {{
    background: {p['bg_active']};
    color: {p['text_primary']};
}}
```

- [ ] **Step 7: Commit**

```bash
git add src/mbforge/ui/theme.py
git commit -m "refactor(ui): replace warm palette with pure black/white/gray"
```

### Task 2: 更新 components.py 颜色引用

**Files:**
- Modify: `src/mbforge/ui/components.py:93-116`

- [ ] **Step 1: 更新 IconButton 样式**

IconButton 的 hover 背景和文字色使用新的灰色系：

```python
self.setStyleSheet(f"""
    QPushButton {{
        background: transparent;
        color: {p['text_secondary']};
        border: none;
        border-radius: {RADIUS_DEFAULT};
        padding: 4px 8px;
        font-size: {FONT_SIZE_DEFAULT};
    }}
    QPushButton:hover {{
        background: {p['bg_hover']};
        color: {p['text_primary']};
    }}
""")
```

- [ ] **Step 2: 更新 StatusBadge 颜色映射**

将棕色系改为灰色：

```python
colors = {
    "online": (p["success"], "#ffffff"),
    "offline": (p["text_secondary"], "#ffffff"),
    "warning": (p["text_secondary"], "#ffffff"),
    "error": (p["accent_coral"], "#ffffff"),
    "processing": (p["accent"], "#ffffff"),
}
```

- [ ] **Step 3: 更新 ProgressBar 样式**

进度条色块改为 `#000000`：

```python
QProgressBar::chunk {{
    background: {p['accent']};
    border-radius: 4px;
}}
```

- [ ] **Step 4: Commit**

```bash
git add src/mbforge/ui/components.py
git commit -m "refactor(ui): update components to pure B&W palette"
```

---

## Batch 2: 主窗口重构

### Task 3: 重构 main_window.py 顶部 Tab 导航

**Files:**
- Modify: `src/mbforge/ui/main_window.py:215-322`

- [ ] **Step 1: 分析现有 `_setup_ui` 结构**

现有布局为 QSplitter 水平三栏（左侧文件树 + 中间标签页 + 右侧 KB/Chat），需重构为：
- 顶部 QTabWidget（Explorer / Search / Chat / Molecular / Workflow / UniDock）
- 底部状态栏
- 每个 Tab 承载不同功能区域

- [ ] **Step 2: 重写 `_setup_ui` 方法**

删除 `self.left_panel`、`self.right_panel`、`self.splitter`，新增 `self.main_tabs`：

```python
def _setup_ui(self) -> None:
    central = QWidget()
    self.setCentralWidget(central)
    main_layout = QVBoxLayout(central)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)

    # 顶部 Tab 导航（替代原来的 left + right panel）
    self.main_tabs = QTabWidget()
    self.main_tabs.setDocumentMode(True)
    self.main_tabs.setStyleSheet(f"""
        QTabWidget {{ background: {p['bg_base']}; }}
        QTabBar {{
            background: {p['bg_surface']};
            border-bottom: 1px solid {p['border']};
        }}
        QTabBar::tab {{
            background: transparent;
            color: {p['text_secondary']};
            padding: 10px 20px;
            font-size: 13px;
            border: none;
            border-bottom: 2px solid transparent;
        }}
        QTabBar::tab:selected {{
            color: {p['text_primary']};
            border-bottom: 2px solid {p['accent']};
        }}
        QTabBar::tab:hover {{
            background: {p['bg_hover']};
        }}
    """)

    # Explorer Tab：文件树 + 扫描/索引按钮
    self._setup_explorer_tab()
    self.main_tabs.addTab(self.explorer_tab, "Explorer")

    # Search Tab：KB 检索
    self._setup_search_tab()
    self.main_tabs.addTab(self.search_tab, "Search")

    # Chat Tab：LLM 对话
    self._setup_chat_tab()
    self.main_tabs.addTab(self.chat_tab, "Chat")

    # Molecular Tab：分子数据库
    self._setup_molecular_tab()
    self.main_tabs.addTab(self.molecular_tab, "Molecular")

    # Workflow Tab：工作流
    self._setup_workflow_tab()
    self.main_tabs.addTab(self.workflow_tab, "Workflow")

    main_layout.addWidget(self.main_tabs, 1)
```

- [ ] **Step 3: 实现 `_setup_explorer_tab` 方法**

```python
def _setup_explorer_tab(self) -> None:
    """Explorer Tab：文件树 + 项目操作按钮."""
    self.explorer_tab = QWidget()
    layout = QVBoxLayout(self.explorer_tab)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(8)

    # 项目标题
    self.project_label = create_label("未打开项目", level="header")
    self.project_label.setStyleSheet(
        f"font-size: 16px; font-weight: 600; "
        f"color: {ThemeManager.instance().get_color('text_primary')};"
    )
    layout.addWidget(self.project_label)

    # 操作按钮行
    btn_row = QHBoxLayout()
    self.home_btn = create_button("Home", style="default")
    self.home_btn.setStyleSheet(f"padding: 6px 12px; font-size: 12px; background: {ThemeManager.instance().get_color('bg_hover')}; border: 1px solid {ThemeManager.instance().get_color('border')}; border-radius: 6px;")
    self.home_btn.clicked.connect(self._go_home)
    self.scan_btn = create_button("扫描")
    self.scan_btn.clicked.connect(self._scan_project)
    self.index_btn = create_button("索引")
    self.index_btn.clicked.connect(self._index_project)
    btn_row.addWidget(self.home_btn)
    btn_row.addWidget(self.scan_btn)
    btn_row.addWidget(self.index_btn)
    btn_row.addStretch()
    layout.addLayout(btn_row)

    # 文件树（CardWidget 承载）
    file_tree_inner = FileTreeWidget()
    file_tree_inner.file_opened.connect(self._open_file)
    file_tree_inner.file_selected.connect(self._index_single_file)
    self.file_tree_card = CardWidget(title="文件", parent=self)
    self.file_tree_card.set_content(file_tree_inner)
    layout.addWidget(self.file_tree_card, 1)
```

- [ ] **Step 4: 实现 `_setup_search_tab` 方法**

```python
def _setup_search_tab(self) -> None:
    """Search Tab：知识库检索."""
    self.search_tab = QWidget()
    layout = QVBoxLayout(self.search_tab)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)

    title = create_label("知识库检索", level="header")
    layout.addWidget(title)

    self.kb_search_input = SearchBox(placeholder="输入查询...")
    self.kb_search_input.returnPressed.connect(self._search_kb)
    layout.addWidget(self.kb_search_input)

    self.kb_results = create_label("输入查询词并按回车搜索", level="body")
    self.kb_results.setWordWrap(True)
    p = ThemeManager.instance().palette()
    self.kb_results.setStyleSheet(
        f"color: {p['text_secondary']}; background: {p['bg_surface']}; padding: 12px; "
        f"border-radius: 8px; font-size: 13px;"
    )
    self.kb_results.setAlignment(Qt.AlignmentFlag.AlignTop)
    layout.addWidget(self.kb_results, 1)
```

- [ ] **Step 5: 实现 `_setup_chat_tab` 方法**

```python
def _setup_chat_tab(self) -> None:
    """Chat Tab：LLM 对话."""
    self.chat_tab = QWidget()
    layout = QVBoxLayout(self.chat_tab)
    layout.setContentsMargins(0, 0, 0, 0)
    chat_inner = ChatWidget()
    layout.addWidget(chat_inner)
    self.chat_widget_ref = chat_inner  # 保持引用
```

- [ ] **Step 6: 实现 `_setup_molecular_tab` 和 `_setup_workflow_tab` 方法**

占位 Tab，打开面板时填充内容：

```python
def _setup_molecular_tab(self) -> None:
    self.molecular_tab = QWidget()
    layout = QVBoxLayout(self.molecular_tab)
    layout.setContentsMargins(16, 16, 16, 16)
    empty = EmptyStateWidget(
        title="分子数据库",
        subtitle="从工具菜单或快捷键打开分子数据库面板",
    )
    layout.addWidget(empty, 1)

def _setup_workflow_tab(self) -> None:
    self.workflow_tab = QWidget()
    layout = QVBoxLayout(self.workflow_tab)
    layout.setContentsMargins(16, 16, 16, 16)
    empty = EmptyStateWidget(
        title="工作流中心",
        subtitle="从工具菜单打开工作流面板",
    )
    layout.addWidget(empty, 1)
```

- [ ] **Step 7: 删除旧的 `_setup_toolbar` 中的跳转按钮**

`QToolBar` 只保留工具按钮，移除文字跳转（Explorer/Search/Chat/Molecular），这些现在由 Tab 承载。

- [ ] **Step 8: 更新 `_go_home` 方法**

欢迎页改为切换到 Explorer Tab（index 0）：

```python
def _go_home(self):
    self.main_tabs.setCurrentIndex(0)
```

- [ ] **Step 9: 更新 `_search_kb` 引用**

`self.kb_results` 和 `self.kb_search_input` 已移到 Search Tab，直接使用。

- [ ] **Step 10: 更新 `_show_mol_db` / `_show_kb_panel` / `_show_todo_panel` / `_show_workflow_panel`**

这些方法改为在对应的 Tab 中显示内容或打开对话框：

```python
def _show_mol_db(self):
    if self.mol_db is None:
        QMessageBox.warning(self, "提示", "请先打开项目")
        return
    self.main_tabs.setCurrentIndex(3)  # Molecular Tab
    # 实际填充 panel 的逻辑...

def _show_kb_panel(self):
    self.main_tabs.setCurrentIndex(1)  # Search Tab

def _show_workflow_panel(self):
    self.main_tabs.setCurrentIndex(4)  # Workflow Tab
```

- [ ] **Step 11: 更新 `_on_theme_changed` 方法**

删除 `self.home_btn` 和 `self.project_label` 的硬编码样式更新（已在 Tab 内）。

- [ ] **Step 12: Commit**

```bash
git add src/mbforge/ui/main_window.py
git commit -m "refactor(ui): replace 3-panel layout with VS Code top tab navigation"
```

---

## Batch 3: 对话框统一

### Task 4: 更新 dialogs.py 所有颜色引用

**Files:**
- Modify: `src/mbforge/ui/dialogs/dialogs.py`

- [ ] **Step 1: 确认无棕色色值**

grep 搜索 `accent_amber`、`brand_primary`、`accent_coral` 在 dialogs.py 中的使用，替换为 `text_secondary` 或 `accent`。

- [ ] **Step 2: 更新 _build_dialog_qss 中的按钮样式**

```python
QPushButton {{
    background: {p['bg_hover']};
    color: {p['text_primary']};
    border: 1px solid {p['border']};
    border-radius: 6px;
    padding: 6px 16px;
}}
QPushButton:hover {{ background: {p['bg_active']}; }}
```

- [ ] **Step 3: Commit**

```bash
git add src/mbforge/ui/dialogs/dialogs.py
git commit -m "refactor(ui): update dialog colors to B&W palette"
```

### Task 5: 更新 unidock_dialog.py

**Files:**
- Modify: `src/mbforge/ui/dialogs/unidock_dialog.py`

- [ ] **Step 1: 读取并替换色值引用**

- [ ] **Step 2: Commit**

```bash
git add src/mbforge/ui/dialogs/unidock_dialog.py
git commit -m "refactor(ui): update unidock dialog to B&W palette"
```

---

## Batch 4: PDF 查看器 & 高亮工具栏

### Task 6: 更新 viewer.py

**Files:**
- Modify: `src/mbforge/ui/pdf_viewer/viewer.py`

- [ ] **Step 1: 检查所有 QSS 字符串中的棕色引用**

- [ ] **Step 2: Commit**

```bash
git add src/mbforge/ui/pdf_viewer/viewer.py
git commit -m "refactor(ui): update PDF viewer colors"
```

### Task 7: 更新 highlight_toolbar.py

**Files:**
- Modify: `src/mbforge/ui/pdf_viewer/highlight_toolbar.py`

- [ ] **Step 1: 确认颜色 swatch 使用新灰色系**

- [ ] **Step 2: Commit**

```bash
git add src/mbforge/ui/pdf_viewer/highlight_toolbar.py
git commit -m "refactor(ui): update highlight toolbar to B&W palette"
```

### Task 8: 更新 detection_popup.py

**Files:**
- Modify: `src/mbforge/ui/pdf_viewer/detection_popup.py`

- [ ] **Step 1: 将 `accent_amber` 替换为 `text_secondary`**

置信度数值显示改用 `text_secondary` 色，不使用强调色：

```python
moldet_row.value_label.setStyleSheet(
    f"color: {p['text_secondary']}; font-weight: 600; font-size: 13px;"
)
```

- [ ] **Step 2: Commit**

```bash
git add src/mbforge/ui/pdf_viewer/detection_popup.py
git commit -m "refactor(ui): update detection popup to B&W palette"
```

---

## Batch 5: 功能面板统一

### Task 9: 更新所有 panels/*.py 文件

**Files:**
- Modify: `src/mbforge/ui/panels/welcome.py`
- Modify: `src/mbforge/ui/panels/pdf_library.py`
- Modify: `src/mbforge/ui/panels/mol.py`
- Modify: `src/mbforge/ui/panels/kb.py`
- Modify: `src/mbforge/ui/panels/todo.py`
- Modify: `src/mbforge/ui/panels/workflow.py`
- Modify: `src/mbforge/ui/panels/status_indicator.py`

- [ ] **Step 1: 逐个检查并替换棕色色值**

对每个文件 grep 搜索棕色引用并替换。

- [ ] **Step 2: Commit**

```bash
git add src/mbforge/ui/panels/
git commit -m "refactor(ui): update all panels to B&W palette"
```

---

## 最终验收

- [ ] 所有棕色/暖色色值已移除（grep 验证 `8B6F47`、`A8895F`、`C49A3C`、`C26B4A` 返回空）
- [ ] 顶部 Tab 导航正常切换，所有 6 个 Tab 可访问
- [ ] 文件树、KB 检索、Chat 三大功能分别在 Explorer/Search/Chat Tab 中正常工作
- [ ] 对话框按钮点击反馈正常
- [ ] ruff check 通过，无 import 错误
- [ ] 启动 GUI 无崩溃：`mbforge gui`
