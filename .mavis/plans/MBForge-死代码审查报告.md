# MBForge 死代码审查报告

**项目**：MBForge
**审查日期**：2026-05-25
**审查工具**：ruff（`uv run ruff check src/`）
**审查范围**：`src/mbforge/`

---

## 一、执行摘要

本次审查由三个并行 track 组成，共发现 **1152 处**问题：

| 严重度 | 类别 | 数量 | 修复方式 |
|--------|------|------|----------|
| 🔴 运行时错误 | F821 未定义名字 | 9 | 手动修复 |
| 🟡 代码缺陷 | F841 未使用变量 | 2 | 手动修复 |
| 🟡 代码缺陷 | B007 未使用循环变量 | 4 | 手动修复 |
| 🟡 代码缺陷 | B027 空 abstract 方法 | 3 | 手动修复 |
| 🟡 架构问题 | NotImplementedError TODO | 3 | 手动修复 |
| 🟡 复杂度 | C901 函数超复杂 | 14 | 计划重构 |
| 🟢 整洁度 | F401 未使用 import | 17 | 15 个 auto-fix |
| ⚪ 风格债务 | 废弃类型注解（UP/SIM/B033） | 1123 | 997 个 auto-fix |

---

## 二、F821 未定义名字（运行时必报错，共 9 处）

**影响**：这些代码若被执行，Python 会抛出 `NameError`，导致应用崩溃。

| 文件 | 行号 | 代码 | 问题说明 | 修复建议 |
|------|------|------|----------|----------|
| `parsers/mol_image_pipeline.py` | 105 | `self.model: Optional[Any] = None` | `Any` 未从 `typing` 导入 | 添加 `from typing import Any` |
| `plugins/cadd_template/plugin.py` | 577 | `def register_tools(self, registry: "ToolRegistry")` | `ToolRegistry` 未导入 | 添加 `from ...agent.tools import ToolRegistry` |
| `plugins/registry.py` | 120 | `def get_tools_registry(self, tool_registry: "ToolRegistry")` | `ToolRegistry` 未导入 | 添加 `from ..agent.tools import ToolRegistry` |
| `plugins/registry.py` | 125 | `def create_panels(self, parent: "QWidget") -> Dict[str, "QWidget"]` | `QWidget` 未导入 | 添加 `from PyQt6.QtWidgets import QWidget` |
| `plugins/registry.py` | 127 | `panels: Dict[str, "QWidget"] = {}` | `QWidget` 未导入（同上） | 同上 |
| `ui/main_window.py` | 138 | `self.project: Optional[Project] = None` | `Project` 未导入 | 添加 `from ..core.project import Project` |
| `ui/main_window.py` | 139 | `self.kb: Optional[KnowledgeBase] = None` | `KnowledgeBase` 未导入 | 添加 `from ..core.knowledge_base import KnowledgeBase` |
| `ui/main_window.py` | 140 | `self.mol_db: Optional[MoleculeDatabase] = None` | `MoleculeDatabase` 未导入 | 添加 `from ..core.mol_database import MoleculeDatabase` |
| `ui/main_window.py` | 141 | `self.todo_manager: Optional[TodoManager] = None` | `TodoManager` 未导入 | 添加 `from ..core.todo_manager import TodoManager` |

**优先级**：P0 — 立即手动修复。

---

## 三、F841 未使用变量（2 处）

| 文件 | 行号 | 代码 | 说明 | 修复建议 |
|------|------|------|------|----------|
| `ui/mol_editor.py` | 232 | `new_idx = rwmol.AddAtom(Chem.Atom(...))` | `new_idx` 被赋值但从未读取 | 改为 `rwmol.AddAtom(Chem.Atom(...))` 或 `_ = ...` |
| `ui/mol_editor_items.py` | 437 | `base = QColor(r, g, b, 220)` | `base` 定义后未使用 | 删除该行 |

**优先级**：P1 — 手动修复。

---

## 四、B007 未使用循环变量（4 处）

| 文件 | 行号 | 代码 | 说明 | 修复建议 |
|------|------|------|------|----------|
| `csar/analyzer.py` | 198 | `for atom_idx, chain_atoms in side_chains.items()` | `chain_atoms` 从未读取 | 改为 `for atom_idx, _ in side_chains.items()` |
| `molecules/schema.py` | 337 | `for smiles, group in seen.items()` | `smiles` 从未读取 | 改为 `for _, group in seen.items()` |
| `parsers/molecule_extractor.py` | 101 | `for idx, (act, act_pos) in enumerate(...)` | `act` 从未读取 | 改为 `for idx, (_, act_pos) in enumerate(...)` |
| `plugins/registry.py` | 48 | `for finder, name, ispkg in pkgutil.iter_modules(...)` | `finder` 从未使用 | 改为 `for _, name, ispkg in pkgutil.iter_modules(...)` |

**优先级**：P2 — 手动修复（`ruff --fix` 可处理部分）。

---

## 五、B027 空 abstract 方法（3 处）

**文件**：`plugins/base.py`

| 行号 | 方法 | 说明 | 建议 |
|------|------|------|------|
| 87 | `BasePlugin.teardown` | 空方法，无 `@abstractmethod` | 明确 docstring："子类按需覆盖，默认空操作" |
| 93 | `BasePlugin.register_tools` | 空方法，无 `@abstractmethod` | 同上 |
| 117 | `BasePlugin.register_cli` | 空方法，无 `@abstractmethod` | 同上 |

**优先级**：P2 — 添加 docstring 消除警告，或加 `@abstractmethod` 强制子类实现。

---

## 六、NotImplementedError TODO（3 处）

**文件**：`plugins/cadd_template/plugin.py`

| 行号 | 方法 | 说明 |
|------|------|------|
| 314 | PDBQT 转换 | 现有实现仅用 `MolToPDBBlock`，TODO 使用 meeko 或 openbabel |
| 443 | AMBER sander/pmemd 调用 | 抛出 `NotImplementedError` |
| 502 | SOMD FEP 调用 | 抛出 `NotImplementedError` |

**优先级**：P1 — 明确未实现则删除接口，或补全实现。

---

## 七、C901 函数复杂度超标（14 处）

| 文件 | 函数 | 复杂度 | 建议 |
|------|------|--------|------|
| `csar/io/reader.py` | `read_excel` | **20** | 拆分 Excel 读取与数据转换 |
| `csar/vis/renderer.py` | `render_sar_path_image` | **18** | 拆分渲染逻辑 |
| `molecules/standardizer.py` | `standardize` | **18** | 拆分标准化各步骤 |
| `csar/preprocessor.py` | `process` | **16** | 拆分预处理流水线 |
| `parsers/pdf_parser.py` | `parse` | **15** | 拆分解析与提取逻辑 |
| `ui/mol_editor_items.py` | `_build_scene` | **14** | 拆分场景构建步骤 |
| `csar/vis/renderer.py` | `_render_single_table` | **13** | 拆分表格渲染 |
| `ui/pdf_viewer/viewer.py` | `_render_visible_range` | **13** | 拆分渲染与滚动逻辑 |
| `csar/io/cas_resolver.py` | `resolve` | **12** | 拆分查询与缓存逻辑 |
| `csar/main.py` | `run_workflow` | **12** | 拆分工作流调度 |
| `clustering/mcs_finder.py` | `find_substitution_positions` | **12** | 拆分查找算法 |
| `agent/executor.py` | `find_documents` | **11** | 拆分文档检索逻辑 |
| `parsers/molecule_extractor.py` | `extract_from_text` | **11** | 拆分提取与后处理 |
| `ui/todo_panel.py` | `refresh` | **11** | 拆分 UI 更新与数据加载 |

**优先级**：P2 — 纳入技术债务，计划重构。

---

## 八、F401 未使用 import（17 处）

| 文件 | 行号 | 内容 | 修复方式 |
|------|------|------|----------|
| `molecules/esmiles.py` | 15 | `AllChem` | auto-fix |
| `parsers/mol_image_pipeline.py` | 37 | `ultralytics` | auto-fix |
| `parsers/mol_image_pipeline.py` | 46 | `molscribe` | auto-fix |
| `plugins/base.py` | 12 | `abstractmethod` | auto-fix |
| `plugins/cadd_template/plugin.py` | 19 | `shutil` | auto-fix |
| `ui/chat_widget.py` | 23 | `log_exception` | auto-fix |
| `ui/components.py` | 25 | `RADIUS_LARGE` | auto-fix |
| `ui/main_window.py` | 27 | `log_call` | auto-fix |
| `ui/main_window.py` | 620 | `Project`（函数内导入） | auto-fix |
| `ui/mol_editor.py` | 25 | `RingTagGraphicsItem` | auto-fix |
| `ui/mol_editor.py` | 26 | `TagGraphicsItem` | auto-fix |
| `ui/mol_editor_dock.py` | 19 | `QSizePolicy` | auto-fix |
| `ui/mol_editor_dock.py` | 20 | `QSlider` | auto-fix |
| `ui/status_dashboard.py` | 9 | `QLabel` | auto-fix |
| `ui/status_indicator.py` | 7 | `Qt` | auto-fix |
| `ui/status_indicator.py` | 8 | `QToolTip` | auto-fix |
| `utils/logger.py` | 16 | `threading` | auto-fix |

**修复命令**：`uv run ruff check src/ --select F401 --fix`

---

## 九、废弃类型注解与代码风格（1123 处）

### 按类型分布

| 类型 | 数量 | 说明 |
|------|------|------|
| UP006 | ~621 | 内联类型注解中使用废弃的 `List`/`Dict`/`Tuple` |
| UP045 | ~320 | 使用 `Optional[X]` 而非现代写法 `X \| None` |
| UP035 | ~129 | 从 `typing` 导入废弃的类型别名 |
| UP037 | ~30 | 类型注解中不必要的字符串引用 |
| UP015 | ~17 | `open()` 多余的 mode 参数 |
| SIM103/SIM105/SIM108 | ~7 | 可简化的 if-else / try-except-pass |
| B033 | 1 | `core/summarizer.py:311` 集合中 `"activity"` 重复 |

### 按模块分布

| 模块 | 错误数 | 占比 | 说明 |
|------|--------|------|------|
| `csar/` | ~225 | ~20% | SAR 分析模块，类型注解密集 |
| `molecules/` | ~180 | ~16% | 分子处理模块 |
| `models/` | ~110 | ~10% | AI 模型抽象层 |
| `parsers/` | ~158 | ~14% | PDF 解析模块 |
| `ui/` | ~125 | ~11% | PyQt6 UI 层 |
| `plugins/` | ~100 | ~9% | 插件系统 |
| 其他 | ~225 | ~20% | utils/core/agent 等 |

### 典型案例

**UP006 — 废弃集合类型注解**
```python
# 当前
def _call_llm(self, messages: List[Message]) -> Any:

# 应改为
def _call_llm(self, messages: list[Message]) -> Any:
```

**UP045 — 旧式 Optional 语法**
```python
# 当前
def from_molecule(cls, mol, activity_type: Optional[str] = "") -> "MoleculeRecord":

# 应改为
def from_molecule(cls, mol, activity_type: str | None = None) -> MoleculeRecord:
```

**UP015 — 多余 open mode**
```python
# 当前
with open(index_path, "r", encoding="utf-8") as f:

# 应改为（默认已是 "r"）
with open(index_path, encoding="utf-8") as f:
```

**SIM105 — 可简化的 try-except-pass**
```python
# 当前
try:
    self._conn.execute(idx_sql)
except sqlite3.OperationalError:
    pass

# 应改为
from contextlib import suppress
with suppress(sqlite3.OperationalError):
    self._conn.execute(idx_sql)
```

**B033 — 集合重复元素**
```python
# src/mbforge/core/summarizer.py:311
keywords = {
    "results", "method", "activity",   # ← 第一次
    "compound", "molecular", "cell",
    "protein", "activity",             # ← 重复！
    "analysis", "data"
}
```

### 整体评估

**严重程度：中等**

- 997/1123（89%）可通过 `ruff --fix` 自动修复
- UI 模块问题占比实际低于预期（~11%）
- 不影响运行时行为，纯代码风格债务
- 建议在 CI 中集成 ruff，阻止新增废弃类型注解

**自动修复命令**：
```bash
# 主要风格问题
uv run ruff check src/ --fix --select UP006,UP035,UP037,UP045,UP015

# 需要 unsafe-fixes
uv run ruff check src/ --fix --unsafe-fixes --select SIM103,SIM105,SIM108
```

---

## 十、TODO 空实现（4 处）

| 文件 | 行号 | 内容 | 影响 |
|------|------|------|------|
| `core/document.py` | 97 | PDF 表格提取，camelot/tabula 未集成，当前返回空列表 | PDF 表格数据丢失 |
| `ui/pdf_viewer/viewer.py` | 878 | 分子确认后接入数据库，当前仅 `logger.info` | 用户确认的分子无法持久化 |
| `ui/kb_panel.py` | 218 | 知识库重索引，当前 `pass` | 无法重建索引 |
| `ui/pdf_library.py` | 217 | PDF 重索引，当前 `pass` | 无法重建索引 |

---

## 十一、修复优先级总结

| 优先级 | 行动 | 工作量 |
|--------|------|--------|
| **P0** | 修复 9 个 F821 运行时错误（手动） | 9 处 |
| **P1** | 修复 5 个 NotImplementedError（删除或补全） | 5 处 |
| **P2** | 修复 F841/B007/B027（手动，16 处） | 16 处 |
| **P2** | 纳入 14 个 C901 超复杂函数为技术债务 | 计划重构 |
| **P3** | `ruff --fix` 一键清理 F401 | 自动，15 处 |
| **P4** | `ruff --fix` 一键清理风格问题（UP/SIM） | 自动，997 处 |
| **P5** | 补全 4 个 TODO 空实现 | 手动评估 |

---

*报告生成：2026-05-25，工具：ruff + 多 Agent 并行审查*
