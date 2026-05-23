# MBForge UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign MBForge PyQt6 UI with a cohesive "Precision Scientific" aesthetic — light/dark themes with system-following + manual override.

**Architecture:** `ThemeManager` becomes a singleton class holding a `theme_changed` pyqtSignal. Two palette dicts (light/dark) keyed by token names. All widget styles reference palette values at construction time. System dark mode detected via `QStyleHints.colorScheme()`, with manual override persisted in `ProjectSettings`.

**Tech Stack:** PyQt6, Python 3, QSS (Qt Style Sheets)

---

## File Map

| File | Responsibility |
|---|---|
| `src/mbforge/ui/theme.py` | Palette dicts, `ThemeManager` class, all factory functions |
| `src/mbforge/core/settings.py` | Add `theme_override` field to `ProjectSettings` |
| `src/mbforge/ui/components.py` | `StatusBadge`, `InfoRow`, `EmptyStateWidget`, `SectionHeader` |
| `src/mbforge/ui/status_indicator.py` | 4 service dots with tooltips |
| `src/mbforge/ui/main_window.py` | Top bar, main module tabs, home button, status bar |
| `src/mbforge/ui/welcome_widget.py` | Cards, recent projects, system stats |
| `src/mbforge/ui/chat_widget.py` | Message bubbles, input area |
| `src/mbforge/ui/kb_panel.py` | Fragment list, detail panel |
| `src/mbforge/ui/pdf_library.py` | PDF list, preview panel, dual empty state |
| `src/mbforge/ui/mol_panel.py` | Table, structure preview |
| `src/mbforge/ui/pdf_viewer.py` | Toolbar, page navigation |
| `src/mbforge/ui/file_tree.py` | Tree item styles |
| `src/mbforge/ui/todo_panel.py` | List items, progress |
| `src/mbforge/ui/dialogs.py` | Dialog styling |

---

## Phase 1: Foundation — theme.py + ThemeManager

### Task 1: Define light/dark palette dicts in theme.py

**Files:**
- Modify: `src/mbforge/ui/theme.py:22-39` (replace COLOR_* constants with palette dicts)

- [ ] **Step 1: Replace flat color constants with palette dicts**

Delete lines 22-38 (the flat `COLOR_* = "..."` constants) and replace with:

```python
# ---------- Palette: Light Mode ----------
LIGHT_PALETTE = {
    "brand_primary": "#0F4C81",
    "brand_primary_light": "#3D5A80",
    "brand_primary_deep": "#0A3A62",
    "accent_amber": "#F4A261",
    "accent_coral": "#E76F51",
    "success": "#2A9D8F",
    "bg_base": "#F7F9FC",
    "bg_card": "#FFFFFF",
    "bg_hover": "#EDF2F7",
    "bg_zebra": "#F0F4F8",
    "text_primary": "#1D3557",
    "text_secondary": "#7A8A9C",
    "border": "#E9ecef",
    "border_focus": "#0F4C81",
}

# ---------- Palette: Dark Mode ----------
DARK_PALETTE = {
    "brand_primary": "#4A90D9",
    "brand_primary_light": "#6BA3D6",
    "brand_primary_deep": "#1D3557",
    "accent_amber": "#F4A261",
    "accent_coral": "#E76F51",
    "success": "#2A9D8F",
    "bg_base": "#0F1419",
    "bg_card": "#1A1F26",
    "bg_hover": "#2A3441",
    "bg_zebra": "#1A2430",
    "text_primary": "#E8EDF2",
    "text_secondary": "#6B7A8C",
    "border": "#2A3441",
    "border_focus": "#4A90D9",
}
```

- [ ] **Step 2: Add size/constants section (keep existing)**
  - Lines 40-50 (`RADIUS_*`, `PADDING_*`, `FONT_SIZE_*`) remain unchanged

- [ ] **Step 3: Commit**

```bash
git add src/mbforge/ui/theme.py
git commit -m "refactor(theme): replace flat COLOR_* constants with LIGHT_PALETTE and DARK_PALETTE dicts"
```

---

### Task 2: Rewrite ThemeManager as a signal-emitting singleton

**Files:**
- Modify: `src/mbforge/ui/theme.py:368-385` (replace static-only class with signal-emitting singleton)

- [ ] **Step 1: Add PyQt6 imports at top of file**

Add to imports section (after line 6):

```python
from PyQt6.QtCore import QObject, pyqtSignal
```

- [ ] **Step 2: Replace ThemeManager class body**

Replace the entire `ThemeManager` class (lines 368-385) with:

```python
class ThemeManager(QObject):
    """全局主题管理器 — 单例模式，持有当前调色板，主题变更时发射信号."""

    theme_changed = pyqtSignal(str)  # emits "light" or "dark"

    _instance: Optional["ThemeManager"] = None

    def __init__(self):
        super().__init__()
        self._palette: dict = LIGHT_PALETTE.copy()
        self._mode: str = "light"
        # Bind to system color scheme changes
        from PyQt6.QtGui import QGuiApplication
        app = QGuiApplication.instance()
        if app:
            app.styleHints().colorSchemeChanged.connect(self._on_system_color_scheme_changed)

    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def mode(self) -> str:
        """Return "light" or "dark"."""
        return self._mode

    def is_dark(self) -> bool:
        return self._mode == "dark"

    def palette(self) -> dict:
        """Return current palette dict (read-only copy)."""
        return self._palette.copy()

    def get_color(self, key: str) -> str:
        """Get a color token value from current palette."""
        return self._palette.get(key, "#000000")

    def set_mode(self, mode: str) -> None:
        """Set theme mode: "light", "dark", or "system"."""
        if mode == "system":
            self._apply_system_mode()
        else:
            self._set_mode(mode)

    def _set_mode(self, mode: str) -> None:
        if mode == self._mode:
            return
        self._mode = mode
        self._palette = DARK_PALETTE.copy() if mode == "dark" else LIGHT_PALETTE.copy()
        self.theme_changed.emit(mode)

    def _on_system_color_scheme_changed(self) -> None:
        """Called when system dark/light mode changes."""
        self._apply_system_mode()

    def _apply_system_mode(self) -> None:
        """Read system preference and apply."""
        from PyQt6.QtGui import QGuiApplication
        app = QGuiApplication.instance()
        if app:
            system = app.styleHints().colorScheme()
            # Qt.ColorScheme.Dark = 1, Light = 0
            dark = system.name == "dark"
            self._set_mode("dark" if dark else "light")

    @staticmethod
    def apply_global(widget: QWidget) -> None:
        """对指定 widget 应用全局样式（用于 QMainWindow）."""
        # Stylesheet built lazily from palette at apply time
        qss = _build_global_stylesheet(ThemeManager.instance().palette())
        widget.setStyleSheet(qss)

    @staticmethod
    def apply_dialog(dialog: QWidget) -> None:
        """对对话框应用统一样式."""
        qss = _build_dialog_stylesheet(ThemeManager.instance().palette())
        dialog.setStyleSheet(qss)
```

- [ ] **Step 3: Add helper functions _build_global_stylesheet and _build_dialog_stylesheet**

These replace the hardcoded f-string `_GLOBAL_STYLESHEET` and `STYLESHEET_DIALOG`. Add before the `ThemeManager` class (before line 368):

```python
def _c(key: str) -> str:
    """Shorthand to get current palette color."""
    return ThemeManager.instance().get_color(key)


def _build_global_stylesheet(p: dict) -> str:
    """Build global QSS from a palette dict."""
    return f"""
    QMainWindow {{ background: {p['bg_base']}; }}
    QWidget {{ background: {p['bg_base']}; color: {p['text_primary']}; }}

    QMenuBar {{
        background: {p['brand_primary_deep']};
        color: #ffffff;
        border-bottom: none;
        padding: 0 8px;
    }}
    QMenuBar::item {{
        padding: 8px 14px;
        border-radius: 4px;
        color: #ffffff;
    }}
    QMenuBar::item:selected {{ background: rgba(255,255,255,0.15); }}
    QMenu {{
        background: {p['bg_card']};
        color: {p['text_primary']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        padding: 6px;
    }}
    QMenu::item {{ padding: 6px 20px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {p['bg_hover']}; }}
    QMenu::separator {{ height: 1px; background: {p['border']}; margin: 6px 12px; }}

    QStatusBar {{
        background: {p['bg_base']};
        color: {p['text_secondary']};
        border-top: 1px solid {p['border']};
        padding: 2px 12px;
        font-size: 12px;
    }}

    QSplitter::handle {{ background: {p['border']}; }}
    QSplitter::handle:horizontal {{ width: 2px; }}

    QLabel {{ color: {p['text_primary']}; }}
    """


def _build_dialog_stylesheet(p: dict) -> str:
    return f"""
    QDialog {{ background: {p['bg_card']}; }}
    QLabel {{ color: {p['text_primary']}; }}
    QLineEdit {{
        background: {p['bg_base']};
        color: {p['text_primary']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        padding: 6px 12px;
    }}
    QLineEdit:focus {{ border-color: {p['border_focus']}; }}
    QTextEdit {{
        background: {p['bg_base']};
        color: {p['text_primary']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        padding: 6px 12px;
    }}
    QComboBox {{
        background: {p['bg_base']};
        color: {p['text_primary']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        padding: 6px 12px;
    }}
    QSpinBox, QDoubleSpinBox {{
        background: {p['bg_base']};
        color: {p['text_primary']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        padding: 6px 12px;
    }}
    QPushButton {{
        background: {p['bg_hover']};
        color: {p['text_primary']};
        border: 1px solid {p['border']};
        border-radius: 6px;
        padding: 6px 16px;
    }}
    QPushButton:hover {{ background: {p['border']}; }}
    """
```

- [ ] **Step 4: Remove old `_GLOBAL_STYLESHEET` and `STYLESHEET_DIALOG` constants**
  - Delete lines 268-365 (the old `_GLOBAL_STYLESHEET` f-string and its content) — these are now generated dynamically
  - Remove `STYLESHEET_DIALOG` from the constants section (line ~191-239) — replaced by `_build_dialog_stylesheet`

- [ ] **Step 5: Verify imports**
  - Add `QGuiApplication` to the QtWidgets or QtCore import if not present

- [ ] **Step 6: Test palette switching**
  - Add a temp test block at end of file:
```python
if __name__ == "__main__":
    tm = ThemeManager.instance()
    print(tm.get_color("brand_primary"))  # should print #0F4C81
    tm.set_mode("dark")
    print(tm.get_color("brand_primary"))  # should print #4A90D9
```
  - Run: `cd C:/Users/10954/Desktop/MBForge && python -c "from src.mbforge.ui.theme import ThemeManager; tm = ThemeManager.instance(); print(tm.get_color('brand_primary')); tm.set_mode('dark'); print(tm.get_color('brand_primary'))"`
  - Expected: `#0F4C81` then `#4A90D9`

- [ ] **Step 7: Commit**

```bash
git add src/mbforge/ui/theme.py
git commit -m "refactor(theme): ThemeManager as signal-emitting singleton with light/dark palettes"
```

---

### Task 3: Update factory functions to use palette

**Files:**
- Modify: `src/mbforge/ui/theme.py` — `create_button`, `create_input`, `create_label`, `create_table`, `create_tree`, `CardWidget`, `SearchBox`

- [ ] **Step 1: Update create_button to use palette**

Replace the f-string button stylesheets with calls to `_build_button_stylesheets(p)` helper. Add before `ThemeManager`:

```python
def _build_button_stylesheets(p: dict) -> tuple:
    """Build button stylesheets from palette."""
    primary = f"""
    QPushButton {{
        background: {p['brand_primary']};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 6px 16px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background: {p['brand_primary_light']}; }}
    QPushButton:pressed {{ background: {p['brand_primary_deep']}; }}
    """
    default = f"""
    QPushButton {{
        background: {p['bg_hover']};
        color: {p['text_primary']};
        border: 1px solid {p['border']};
        border-radius: 6px;
        padding: 6px 16px;
    }}
    QPushButton:hover {{ background: {p['border']}; }}
    QPushButton:pressed {{ background: {p['border']}; }}
    """
    danger = f"""
    QPushButton {{
        background: {p['accent_coral']};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 6px 16px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background: #d4563e; }}
    """
    return primary, default, danger
```

- [ ] **Step 2: Update create_button function**

Replace `create_button` function body with:

```python
def create_button(
    text: str,
    style: str = "default",
    parent: Optional[QWidget] = None,
) -> QPushButton:
    btn = QPushButton(text, parent)
    p = ThemeManager.instance().palette()
    primary, default, danger = _build_button_stylesheets(p)
    if style == "primary":
        btn.setStyleSheet(primary)
    elif style == "danger":
        btn.setStyleSheet(danger)
    else:
        btn.setStyleSheet(default)
    return btn
```

- [ ] **Step 3: Update create_label function**

Replace the three `STYLESHEET_LABEL_*` constants and `create_label` function to use palette:

```python
def create_label(
    text: str,
    level: str = "body",
    parent: Optional[QWidget] = None,
) -> QLabel:
    p = ThemeManager.instance().palette()
    label = QLabel(text, parent)
    if level == "header":
        label.setStyleSheet(f"QLabel {{ color: {p['text_primary']}; font-weight: 600; font-size: 14px; }}")
    elif level == "caption":
        label.setStyleSheet(f"QLabel {{ color: {p['text_secondary']}; font-size: 12px; }}")
    else:
        label.setStyleSheet(f"QLabel {{ color: {p['text_primary']}; font-size: 13px; }}")
    return label
```

- [ ] **Step 4: Update create_input function**

```python
def create_input(
    placeholder: str = "",
    password: bool = False,
    parent: Optional[QWidget] = None,
) -> QLineEdit:
    p = ThemeManager.instance().palette()
    edit = QLineEdit(parent)
    edit.setPlaceholderText(placeholder)
    edit.setStyleSheet(f"""
    QLineEdit {{
        background: {p['bg_base']};
        color: {p['text_primary']};
        border: 1px solid {p['border']};
        border-radius: 20px;
        padding: 6px 16px;
        font-size: 13px;
    }}
    QLineEdit:focus {{
        border-color: {p['border_focus']};
        background: {p['bg_card']};
    }}
    """)
    if password:
        edit.setEchoMode(QLineEdit.EchoMode.Password)
    return edit
```

- [ ] **Step 5: Update create_table function**

```python
def create_table(headers: list[str], parent: Optional[QWidget] = None) -> QTableWidget:
    p = ThemeManager.instance().palette()
    table = QTableWidget(parent)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setStyleSheet(f"""
    QTableWidget {{
        background: {p['bg_card']};
        color: {p['text_primary']};
        gridline-color: {p['border']};
        border: 1px solid {p['border']};
        border-radius: 10px;
        outline: none;
    }}
    QHeaderView::section {{
        background: {p['bg_base']};
        color: {p['text_secondary']};
        padding: 8px 12px;
        border: 1px solid {p['border']};
        font-weight: 500;
        font-size: 12px;
    }}
    QTableWidget::item {{
        padding: 6px 10px;
    }}
    QTableWidget::item:selected {{
        background: {p['brand_primary']}1a;
        color: {p['brand_primary']};
    }}
    QTableWidget::item:hover {{
        background: {p['bg_hover']};
    }}
    """)
    return table
```

- [ ] **Step 6: Update create_tree function**

```python
def create_tree(parent: Optional[QWidget] = None) -> QTreeWidget:
    p = ThemeManager.instance().palette()
    tree = QTreeWidget(parent)
    tree.setStyleSheet(f"""
    QTreeWidget {{
        border: none;
        background: {p['bg_base']};
        color: {p['text_primary']};
        outline: none;
    }}
    QTreeWidget::item {{
        padding: 4px 2px;
        border-radius: 4px;
    }}
    QTreeWidget::item:selected {{
        background: {p['brand_primary']}1a;
        color: {p['brand_primary']};
    }}
    QTreeWidget::item:hover {{
        background: {p['bg_hover']};
    }}
    """)
    return tree
```

- [ ] **Step 7: Update CardWidget**

```python
class CardWidget(QFrame):
    def __init__(self, title: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        p = ThemeManager.instance().palette()
        self.setStyleSheet(f"""
        QFrame {{
            background: {p['bg_card']};
            border: 1px solid {p['border']};
            border-radius: 10px;
        }}
        """)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(8)
        if title:
            self._title_label = create_label(title, level="header")
            self._layout.addWidget(self._title_label)
        else:
            self._title_label = None
```

- [ ] **Step 8: Update SearchBox**

```python
class SearchBox(QLineEdit):
    def __init__(self, placeholder: str = "搜索...", parent: Optional[QWidget] = None):
        super().__init__(parent)
        p = ThemeManager.instance().palette()
        self.setPlaceholderText(f"🔍 {placeholder}")
        self.setStyleSheet(f"""
        QLineEdit {{
            background: {p['bg_base']};
            color: {p['text_primary']};
            border: 1px solid {p['border']};
            border-radius: 20px;
            padding: 6px 16px 6px 32px;
            font-size: 13px;
        }}
        QLineEdit:focus {{
            border-color: {p['border_focus']};
            background: {p['bg_card']};
        }}
        """)
        self.setMinimumHeight(32)
```

- [ ] **Step 9: Commit**

```bash
git add src/mbforge/ui/theme.py
git commit -m "refactor(theme): factory functions use palette from ThemeManager"
```

---

## Phase 2: Core Components — components.py

### Task 4: Update StatusBadge, InfoRow, EmptyStateWidget, SectionHeader

**Files:**
- Modify: `src/mbforge/ui/components.py`

- [ ] **Step 1: Add ThemeManager import**

Add to top of file (after existing imports):
```python
from ..ui.theme import ThemeManager
```

- [ ] **Step 2: Update StatusBadge.set_status to use palette**

Read the current `StatusBadge` class in `components.py`. Replace its `set_status` method body to use palette colors:

```python
def set_status(self, status: str) -> None:
    self._status = status if status in self.STYLES else "offline"
    p = ThemeManager.instance().palette()
    colors = {
        "online": (p["success"], "#ffffff"),
        "offline": (p["text_secondary"], "#ffffff"),
        "warning": (p["accent_amber"], "#212529"),
        "error": (p["accent_coral"], "#ffffff"),
        "processing": (p["brand_primary"], "#ffffff"),
    }
    bg, fg = colors.get(self._status, colors["offline"])
    self.setStyleSheet(f"QLabel {{ background: {bg}; color: {fg}; padding: 2px 8px; border-radius: 10px; font-size: 11px; }}")
```

Also update `__init__` to not call `set_status` with hardcoded colors — instead call the updated `set_status("offline")` with no text argument.

- [ ] **Step 3: Update InfoRow**

Replace `InfoRow.__init__` body to use palette for colors:

```python
def __init__(self, key: str, value: str = "", parent: Optional[QWidget] = None):
    super().__init__(parent)
    p = ThemeManager.instance().palette()
    layout = QHBoxLayout(self)
    layout.setContentsMargins(0, 4, 0, 4)
    layout.setSpacing(12)
    self.key_label = QLabel(f"{key}:", parent)
    self.key_label.setStyleSheet(f"color: {p['text_secondary']}; font-size: 12px;")
    self.key_label.setMinimumWidth(80)
    layout.addWidget(self.key_label)
    self.value_label = QLabel(value, parent)
    self.value_label.setStyleSheet(f"color: {p['text_primary']}; font-size: 13px;")
    self.value_label.setWordWrap(True)
    layout.addWidget(self.value_label, 1)
```

- [ ] **Step 4: Update EmptyStateWidget to use palette**

```python
class EmptyStateWidget(QWidget):
    def __init__(self, icon: str = "📭", title: str = "暂无数据",
                 subtitle: str = "", action_text: str = "",
                 action_callback: Optional[Callable[[], None]] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        p = ThemeManager.instance().palette()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)
        icon_label = QLabel(icon, parent)
        icon_label.setStyleSheet("font-size: 48px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        title_label = QLabel(title, parent)
        title_label.setStyleSheet(f"color: {p['text_primary']}; font-size: 16px; font-weight: 600;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        if subtitle:
            sub_label = QLabel(subtitle, parent)
            sub_label.setStyleSheet(f"color: {p['text_secondary']}; font-size: 13px;")
            sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(sub_label)
        if action_text and action_callback:
            from ..ui.theme import create_button
            btn = create_button(action_text, style="primary")
            btn.clicked.connect(action_callback)
            layout.addWidget(btn)
```

- [ ] **Step 5: Update SectionHeader to use palette**

Replace `create_label` call inside `SectionHeader.__init__` to use palette:

```python
self.title_label = QLabel(title, parent)
p = ThemeManager.instance().palette()
self.title_label.setStyleSheet(f"color: {p['text_primary']}; font-weight: 600; font-size: 14px;")
```

- [ ] **Step 6: Commit**

```bash
git add src/mbforge/ui/components.py
git commit -m "refactor(components): StatusBadge, InfoRow, EmptyStateWidget, SectionHeader use ThemeManager palette"
```

---

### Task 5: Update status_indicator.py service dots

**Files:**
- Modify: `src/mbforge/ui/status_indicator.py`

- [ ] **Step 1: Update ServiceStatusIndicator to use palette for online/offline colors**

Replace the hardcoded `#40c057` / `#868e96` with palette lookups:

```python
def _update_dot(self, name: str) -> None:
    p = ThemeManager.instance().palette()
    if self._status[name] == "online":
        color = p["success"]
    else:
        color = p["text_secondary"]
    self._dots[name].setStyleSheet(f"font-size: 12px; color: {color};")
    status_text = "在线" if self._status[name] == "online" else "离线"
    self._dots[name].setToolTip(f"{name}: {status_text}")
```

- [ ] **Step 2: Commit**

```bash
git add src/mbforge/ui/status_indicator.py
git commit -m "refactor(status_indicator): use palette colors for online/offline dots"
```

---

## Phase 3: Main Window + Panels

### Task 6: Update main_window.py — top bar, main module tabs, home button, status bar

**Files:**
- Modify: `src/mbforge/ui/main_window.py`

- [ ] **Step 1: Update top bar background color**

In `_setup_ui`, find the `top_bar` QWidget styling. Add/override the background:

```python
top_bar.setStyleSheet(f"background: {ThemeManager.instance().get_color('brand_primary_deep')};")
```

- [ ] **Step 2: Update home_btn to use palette**

Find the `home_btn` creation. Replace its inline `setStyleSheet` call:

```python
p = ThemeManager.instance().palette()
self.home_btn = create_button("🏠 首页", style="default")
self.home_btn.setStyleSheet(
    f"padding: 6px 12px; font-size: 12px; background: rgba(255,255,255,0.1); "
    f"color: #ffffff; border: 1px solid rgba(255,255,255,0.2); border-radius: 6px;"
)
```

- [ ] **Step 3: Update status bar labels to use palette**

Find `_setup_statusbar`. Replace the inline `setStyleSheet` calls for `cpu_label` and `mem_label`:

```python
p = ThemeManager.instance().palette()
self.cpu_label.setStyleSheet(f"color: {p['text_secondary']}; padding: 0 4px; font-size: 12px;")
self.mem_label.setStyleSheet(f"color: {p['text_secondary']}; padding: 0 4px; font-size: 12px;")
```

- [ ] **Step 4: Connect ThemeManager theme_changed to refresh status bar colors**

In `__init__`, after creating the status bar, connect:

```python
ThemeManager.instance().theme_changed.connect(self._on_theme_changed)
```

Add method:

```python
def _on_theme_changed(self, mode: str):
    """Refresh widget styles when theme changes."""
    p = ThemeManager.instance().palette()
    self.cpu_label.setStyleSheet(f"color: {p['text_secondary']}; padding: 0 4px; font-size: 12px;")
    self.mem_label.setStyleSheet(f"color: {p['text_secondary']}; padding: 0 4px; font-size: 12px;")
    self.top_bar.setStyleSheet(f"background: {p['brand_primary_deep']};")
    p_home = ThemeManager.instance().palette()
    self.home_btn.setStyleSheet(
        f"padding: 6px 12px; font-size: 12px; background: rgba(255,255,255,0.1); "
        f"color: #ffffff; border: 1px solid rgba(255,255,255,0.2); border-radius: 6px;"
    )
```

- [ ] **Step 5: Apply global theme on startup**

In `__init__`, after `ThemeManager.apply_global(self)` call, also apply system mode:

```python
ThemeManager.apply_global(self)
ThemeManager.instance().set_mode("system")  # follow system by default
```

- [ ] **Step 6: Commit**

```bash
git add src/mbforge/ui/main_window.py
git commit -m "refactor(main_window): top bar, home button, status bar use ThemeManager palette"
```

---

### Task 7: Update welcome_widget.py — cards, recent projects, system stats

**Files:**
- Modify: `src/mbforge/ui/welcome_widget.py`

- [ ] **Step 1: Add ThemeManager import**
```python
from ..ui.theme import ThemeManager
```

- [ ] **Step 2: Update _refresh_recent_projects row styles**

In `_refresh_recent_projects`, find the `setStyleSheet` on the `row` QWidget. Replace with:

```python
p = ThemeManager.instance().palette()
row.setStyleSheet(f"""
    QWidget {{
        background: {p['bg_card']};
        border: 1px solid {p['border']};
        border-radius: 8px;
    }}
    QWidget:hover {{
        background: {p['bg_hover']};
    }}
""")
```

- [ ] **Step 3: Connect theme change signal**

In `_setup_ui`, add:

```python
ThemeManager.instance().theme_changed.connect(self._on_theme_changed)
```

Add method:

```python
def _on_theme_changed(self, mode: str):
    self._setup_ui()
    self._refresh_recent_projects()
    self._refresh_stats()
```

- [ ] **Step 4: Update platform info in _refresh_stats**

The platform info was moved here — ensure it shows correctly in both light/dark by using palette-aware InfoRow (already done in Task 4).

- [ ] **Step 5: Commit**

```bash
git add src/mbforge/ui/welcome_widget.py
git commit -m "refactor(welcome_widget): cards and recent projects use ThemeManager palette"
```

---

### Task 8: Update chat_widget.py — message bubbles, input area

**Files:**
- Modify: `src/mbforge/ui/chat_widget.py`

- [ ] **Step 1: Add ThemeManager import**
```python
from ..ui.theme import ThemeManager
```

- [ ] **Step 2: Update ChatMessageRenderer._wrap_html to use palette CSS variables**

The `_wrap_html` method generates HTML with hardcoded colors. Update to read from ThemeManager and inject as CSS variables:

```python
def _wrap_html(self, body: str) -> str:
    p = ThemeManager.instance().palette()
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    :root {{
        --bg-card: {p['bg_card']};
        --bg-base: {p['bg_base']};
        --bg-hover: {p['bg_hover']};
        --text-primary: {p['text_primary']};
        --text-secondary: {p['text_secondary']};
        --border: {p['border']};
        --brand: {p['brand_primary']};
        --accent: {p['accent_amber']};
        --code-bg: {p['bg_hover']};
    }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        font-size: 14px;
        line-height: 1.7;
        color: var(--text-primary);
        background: transparent;
        padding: 0;
        margin: 0;
        word-wrap: break-word;
    }}
    h1, h2, h3, h4 {{ margin-top: 16px; margin-bottom: 10px; font-weight: 600; }}
    h1 {{ font-size: 20px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }}
    h2 {{ font-size: 17px; border-bottom: 1px solid var(--border); padding-bottom: 5px; }}
    h3 {{ font-size: 15px; }}
    code {{ background: var(--code-bg); padding: 2px 6px; border-radius: 4px; font-family: "Consolas", "Monaco", monospace; font-size: 0.9em; color: {p['accent_coral']}; }}
    pre {{ background: var(--bg-base); padding: 12px; border-radius: 8px; overflow-x: auto; border: 1px solid var(--border); margin: 8px 0; }}
    pre code {{ background: none; padding: 0; color: var(--text-primary); }}
    table {{ border-collapse: collapse; width: 100%; margin: 10px 0; border-radius: 8px; overflow: hidden; border: 1px solid var(--border); font-size: 13px; }}
    th, td {{ border: 1px solid var(--border); padding: 8px 10px; text-align: left; }}
    th {{ background: var(--bg-base); font-weight: 600; }}
    blockquote {{ border-left: 3px solid var(--brand); margin: 8px 0; padding: 8px 14px; background: var(--bg-base); border-radius: 0 8px 8px 0; }}
    a {{ color: var(--brand); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    ul, ol {{ padding-left: 20px; margin: 6px 0; }}
    p {{ margin: 6px 0; }}
</style>
</head>
<body>{body}</body>
</html>"""
```

- [ ] **Step 3: Update ChatMessage._setup_ui body_container background**

In `ChatMessage._setup_ui`, replace hardcoded `bg_color` with palette:

```python
p = ThemeManager.instance().palette()
bg_color = p["bg_hover"] if is_user else p["bg_card"]
```

- [ ] **Step 4: Update input frame background**

In `ChatWidget._setup_ui`, find the `input_frame.setStyleSheet` call. Replace with:

```python
p = ThemeManager.instance().palette()
input_frame.setStyleSheet(f"background: {p['bg_base']}; border-top: 1px solid {p['border']};")
```

- [ ] **Step 5: Connect theme change**

In `ChatWidget.__init__` or `_setup_ui`:

```python
ThemeManager.instance().theme_changed.connect(self._on_theme_changed)
```

Add:

```python
def _on_theme_changed(self, mode: str):
    # Re-render all messages with new palette
    for i in range(self.messages_layout.count() - 1):
        item = self.messages_layout.itemAt(i)
        if item.widget():
            item.widget().deleteLater()
    # Chat history will be restored by agent context
```

- [ ] **Step 6: Commit**

```bash
git add src/mbforge/ui/chat_widget.py
git commit -m "refactor(chat_widget): message bubbles and input use ThemeManager palette"
```

---

### Task 9: Update kb_panel.py, pdf_library.py, mol_panel.py

**Files:**
- Modify: `src/mbforge/ui/kb_panel.py`, `src/mbforge/ui/pdf_library.py`, `src/mbforge/ui/mol_panel.py`

For each file:

- [ ] **Step 1: Add ThemeManager import**
```python
from ..ui.theme import ThemeManager
```

- [ ] **Step 2: Replace all hardcoded hex colors in setStyleSheet calls**
  - Search for patterns like `"#f8f9fa"`, `"#e9ecef"`, `"#1971c2"`, `"#e7f5ff"` etc.
  - Replace each with `ThemeManager.instance().get_color('token_name')` or a `p = ThemeManager.instance().palette()` reference

- [ ] **Step 3: For each widget class, connect theme_changed**
  - In `__init__` or `_setup_ui`: `ThemeManager.instance().theme_changed.connect(self._on_theme_changed)`
  - Add `_on_theme_changed(self, mode)` method that calls `self.refresh()` or reconstructs the widget's stylesheet

- [ ] **Step 4: Specific replacements for pdf_library.py**
  - `QListWidget` stylesheet: `"#ffffff"` → `p["bg_card"]`, `"#f8f9fa"` → `p["bg_hover"]`, `"#e7f5ff"` → `p["brand_primary"] + "1a"`, `"#e9ecef"` → `p["border"]`
  - `QTextEdit` preview: `"#f8f9fa"` → `p["bg_base"]`, `"#e9ecef"` → `p["border"]`
  - Header border-bottom: `"1px solid #e9ecef"` → `f"1px solid {p['border']}"`

- [ ] **Step 5: Commit each file separately**

```bash
git add src/mbforge/ui/kb_panel.py
git commit -m "refactor(kb_panel): use ThemeManager palette"

git add src/mbforge/ui/pdf_library.py
git commit -m "refactor(pdf_library): use ThemeManager palette, dual empty state"

git add src/mbforge/ui/mol_panel.py
git commit -m "refactor(mol_panel): use ThemeManager palette"
```

---

### Task 10: Update pdf_viewer.py, file_tree.py, todo_panel.py

**Files:**
- Modify: `src/mbforge/ui/pdf_viewer.py`, `src/mbforge/ui/file_tree.py`, `src/mbforge/ui/todo_panel.py`

Same pattern as Task 9 — replace hardcoded colors with palette lookups, connect `theme_changed` signal.

- [ ] **Step 1: Commit each file**

```bash
git add src/mbforge/ui/pdf_viewer.py
git commit -m "refactor(pdf_viewer): toolbar and page nav use ThemeManager palette"

git add src/mbforge/ui/file_tree.py
git commit -m "refactor(file_tree): tree items use ThemeManager palette"

git add src/mbforge/ui/todo_panel.py
git commit -m "refactor(todo_panel): list items and progress use ThemeManager palette"
```

---

### Task 11: Update dialogs.py

**Files:**
- Modify: `src/mbforge/ui/dialogs.py`

- [ ] **Step 1: Add ThemeManager import and apply_dialog usage**
- In each dialog class `__init__`, after `super().__init__(parent)`, add: `ThemeManager.apply_dialog(self)`

- [ ] **Step 2: Commit**

```bash
git add src/mbforge/ui/dialogs.py
git commit -m "refactor(dialogs): apply ThemeManager dialog stylesheet"
```

---

## Phase 4: Settings Integration

### Task 12: Add theme_override to ProjectSettings and wire up SettingsDialog

**Files:**
- Modify: `src/mbforge/core/settings.py`
- Modify: `src/mbforge/ui/dialogs.py` (SettingsDialog)

- [ ] **Step 1: Add theme_override to ProjectSettings**

In `ProjectSettings`, add field:
```python
theme_override: str = "system"  # "system" | "light" | "dark"
```

Add to `from_dict`:
```python
theme_override=data.get("theme_override", "system"),
```

- [ ] **Step 2: Add theme picker to SettingsDialog**

Find `SettingsDialog` in `dialogs.py`. Add a "主题" tab (or section) with three radio buttons: [跟随系统 / 浅色 / 深色].

In the tab's layout:
```python
from PyQt6.QtWidgets import QRadioButton, QButtonGroup, QVBoxLayout, QLabel
theme_label = QLabel("主题")
theme_layout = QVBoxLayout()
group = QButtonGroup()
system_btn = QRadioButton("跟随系统")
light_btn = QRadioButton("浅色")
dark_btn = QRadioButton("深色")
group.addButton(system_btn)
group.addButton(light_btn)
group.addButton(dark_btn)
current = self.config.theme_override if hasattr(self.config, 'theme_override') else 'system'
if current == 'light': light_btn.setChecked(True)
elif current == 'dark': dark_btn.setChecked(True)
else: system_btn.setChecked(True)
theme_layout.addWidget(system_btn)
theme_layout.addWidget(light_btn)
theme_layout.addWidget(dark_btn)
```

In `SettingsDialog.accepted` (or `apply` method), save:
```python
if light_btn.isChecked(): mode = 'light'
elif dark_btn.isChecked(): mode = 'dark'
else: mode = 'system'
ThemeManager.instance().set_mode(mode)
```

- [ ] **Step 3: Load theme_override on app startup**

In `main_window.py`'s `__init__`, after `ThemeManager.apply_global(self)`:

```python
# Apply theme override from settings (if any)
if self.project and hasattr(self.project.settings, 'theme_override'):
    ThemeManager.instance().set_mode(self.project.settings.theme_override)
else:
    ThemeManager.instance().set_mode("system")
```

- [ ] **Step 4: Commit**

```bash
git add src/mbforge/core/settings.py src/mbforge/ui/dialogs.py src/mbforge/ui/main_window.py
git commit -m "feat(settings): theme override in ProjectSettings, theme picker in SettingsDialog"
```

---

## Self-Review Checklist

**Spec coverage:**
- [ ] Light/dark palette dicts → Task 1
- [ ] ThemeManager signal + singleton → Task 2
- [ ] System follow via QStyleHints → Task 2
- [ ] is_dark_mode() helper → Task 2
- [ ] Factory functions use palette → Task 3
- [ ] components.py use palette → Task 4
- [ ] status_indicator use palette → Task 5
- [ ] main_window top bar, home btn, status bar → Task 6
- [ ] welcome_widget cards + recent rows → Task 7
- [ ] chat_widget message HTML colors → Task 8
- [ ] kb_panel, pdf_library, mol_panel → Task 9
- [ ] pdf_viewer, file_tree, todo_panel → Task 10
- [ ] dialogs → Task 11
- [ ] Settings theme picker + ProjectSettings theme_override → Task 12

**Placeholder scan:**
- No "TBD" or "TODO" remaining
- All color values specified as actual hex codes or palette token names
- All method names consistent across tasks

**Type consistency:**
- `ThemeManager.instance()` returns `ThemeManager`
- `ThemeManager.set_mode("light"|"dark"|"system")` — consistent
- `ProjectSettings.theme_override: str = "system"` — consistent
- All `theme_changed.emit(mode)` where mode is `"light"` or `"dark"` — consistent
