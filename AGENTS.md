# MBForge - Agent 开发指南

> 本文档面向 AI 编码助手（Agent），提供项目背景、架构概览、开发规范与常用命令。
> 项目主要文档语言为中文，代码注释也以中文为主。

---

## 1. 项目概述

MBForge（Molecular Knowledge Base & AI Workbench）是一款面向药物化学与分子科学的桌面端知识库应用，采用 PyQt6 构建 GUI。核心定位类似 "Obsidian + Zotero" 的分子科学版本：

- **Vault 项目管理**：一个文件夹即一个项目，`.mbforge/` 隐藏目录存储元数据。
- **PDF 解析流水线**：PyMuPDF 提取文本/图片 → 分子识别（SMILES） → LLM 摘要 → ChromaDB 向量索引。
- **知识库检索**：基于 ChromaDB 的语义搜索 + Rerank 重排序。
- **LLM 智能对话**：ReAct Agent，支持工具调用（知识库搜索、分子数据库查询、文档读取等）。
- **分子数据库**：SQLite + RDKit，支持活性数据存储与性质计算。
- **工作流扩展**：预留分子生成、对接、QSAR、分子动力学模块（当前为占位）。

---

## 2. 目录结构

```
MBForge/
├── src/mbforge/              # 主应用源码（setuptools 包根）
│   ├── core/                 # 核心数据模型与业务逻辑
│   │   ├── project.py        # Vault 项目管理、DocumentEntry
│   │   ├── knowledge_base.py # ChromaDB 封装
│   │   ├── mol_database.py   # SQLite + RDKit 分子数据库
│   │   ├── document.py       # 文档提取（PDF/Markdown/Text）
│   │   ├── summarizer.py     # LLM 三层摘要（L0/L1/L2）
│   │   ├── settings.py       # 项目级配置
│   │   ├── memory.py         # Agent 记忆模板
│   │   └── todo_manager.py   # Todo 持久化
│   ├── models/               # AI 模型抽象层
│   │   ├── base.py           # BaseLLM / BaseEmbedder / BaseReranker / BaseVLM
│   │   ├── llm.py            # OpenAI 兼容 LLM
│   │   ├── anthropic_llm.py  # Anthropic Claude
│   │   ├── embedding.py      # sentence-transformers / API Embedding
│   │   ├── rerank.py         # Rerank 模型
│   │   └── vlm.py            # 视觉语言模型
│   ├── parsers/              # PDF 解析与分子提取
│   │   ├── pdf_parser.py     # 解析流水线编排
│   │   ├── molecule_extractor.py
│   │   └── file_processor.py
│   ├── agent/                # ReAct Agent
│   │   ├── agent.py          # ProjectAgent 协调器
│   │   ├── context.py        # LayeredContext 分层上下文
│   │   ├── executor.py       # ToolExecutor + ToolRegistry
│   │   ├── tools.py          # 10 个工具定义
│   │   ├── memory_manager.py # 6 类记忆管理
│   │   ├── trajectory.py     # 工具调用轨迹
│   │   └── archive_agent.py  # 文档检索 Agent
│   ├── ui/                   # PyQt6 图形界面
│   │   ├── theme.py          # 主题管理器 + 样式常量 + 工厂函数
│   │   ├── components.py     # 可复用自定义组件
│   │   ├── main_window.py    # 主窗口（精简版，集成新面板）
│   │   ├── chat_widget.py    # Markdown 渲染版对话面板
│   │   ├── dialogs.py        # 通用对话框
│   │   ├── editor.py         # Markdown 编辑器
│   │   ├── preview.py        # Markdown 预览
│   │   ├── file_tree.py      # 增量更新 + 懒加载文件树
│   │   ├── mol_panel.py      # 分子数据库面板
│   │   ├── mol_renderer.py   # RDKit 分子渲染
│   │   ├── pdf_viewer.py     # 虚拟滚动 PDF 查看器（LRU 缓存优化）
│   │   ├── welcome_widget.py # 欢迎首页
│   │   ├── kb_panel.py       # 知识库管理面板
│   │   ├── todo_panel.py     # TODO 队列管理
│   │   ├── workflow_panel.py # 工作流中心
│   │   └── status_dashboard.py # 状态仪表盘
│   ├── parser_io/            # UniParser API 集成
│   │   ├── client.py
│   │   ├── config.py
│   │   └── models.py
│   ├── workflow/             # 工作流扩展（占位）
│   │   ├── base.py
│   │   ├── generation.py
│   │   ├── docking.py
│   │   ├── qsar.py
│   │   └── md.py
│   ├── utils/                # 工具函数
│   │   ├── config.py         # 全局配置（AppConfig / ModelConfig 等）
│   │   ├── constants.py      # 常量
│   │   ├── helpers.py        # 辅助函数
│   │   ├── logger.py         # 结构化日志
│   │   └── error_logger.py   # 错误日志
│   ├── cli.py                # CLI 入口（mbforge 命令）
│   ├── app.py                # GUI 入口
│   └── __main__.py           # python -m mbforge 入口
├── tests/                    # 测试
│   ├── unit/                 # 单元测试
│   ├── parser_io/            # parser_io 模块测试
│   └── conftest.py           # pytest 配置（将 src 加入 sys.path）
├── setup/                    # 交互式一键配置脚本
│   ├── index.sh / index.bat  # 入口
│   ├── common.sh             # 公共函数
│   └── modules/              # 分模块配置脚本
├── docs/                     # 项目文档
│   ├── ARCHITECTURE.md       # 系统架构设计
│   ├── API.md                # 公共 API 参考
│   ├── TECH_STACK.md         # 技术栈详解
│   └── DEVELOPMENT.md        # 开发指南
├── pyproject.toml            # 项目配置（setuptools + uv workspace）
├── build.py                  # PyInstaller 打包脚本
├── MBForge.spec              # PyInstaller spec
├── .env.template             # 环境变量模板
└── uv.lock                   # uv 锁定文件
```

### 已知目录异常

`pyproject.toml` 中定义的 uv workspace members 为：
- `setup/UniParser-Tools`
- `setup/openSAR`

但这两个目录在文件系统中为空。实际的 `UniParser-Tools/` 和 `openSAR/` 包位于项目根目录下，且各自拥有独立的 `.git/`（可能是子仓库或历史遗留结构）。**修改 workspace 配置或移动目录前需格外谨慎。**

---

## 3. 技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| 语言 | Python >= 3.11 | 使用 `from __future__ import annotations` |
| UI | PyQt6 >= 6.6 + QWebEngineView | 桌面 GUI |
| 向量数据库 | ChromaDB >= 0.4 | PersistentClient 模式，cosine 距离 |
| 化学信息学 | RDKit >= 2024.3 | SMILES 解析、性质计算、2D 渲染 |
| PDF 处理 | PyMuPDF (fitz) >= 1.25 | 文本/图片提取 |
| Embedding | sentence-transformers >= 2.5 | 默认 `BAAI/bge-small-zh-v1.5` |
| LLM 客户端 | openai >= 1.0, anthropic >= 0.103 | 兼容 vLLM / Ollama / 硅基流动等 |
| 深度学习 | PyTorch >= 2.6 (CUDA 12.8) | 本地模型推理 |
| 数据 | SQLite (内置), pandas, numpy | 分子数据库与数据处理 |
| 包管理 | uv |  workspace 与 lock 文件 |
| 测试 | pytest >= 7.0 | 配合 pytest-cov |
| 代码质量 | ruff >= 0.1, mypy >= 1.0 | 格式化、lint、类型检查 |
| 打包 | pyinstaller >= 6.0 | Windows EXE 分发 |

PyTorch 通过自定义 index 安装：`https://download.pytorch.org/whl/cu128`。
uv 使用清华 PyPI 镜像：`https://pypi.tuna.tsinghua.edu.cn/simple`。

---

## 4. 构建与运行命令

### 4.1 环境初始化

```bash
# 安装所有依赖（含 dev）与 workspace members
uv sync --dev

# 复制环境变量模板并编辑
cp .env.template .env
# 配置 UNIPARSER_HOST、LLM API Key 等
```

### 4.2 运行应用

```bash
# 启动 GUI（默认命令）
uv run mbforge
# 或
uv run mbforge gui --project ./my-project

# CLI：初始化项目
uv run mbforge init ./my-project --name "MyProject"

# CLI：索引项目文件
uv run mbforge index ./my-project

# 直接以模块运行
uv run python -m mbforge
```

### 4.3 打包

```bash
# 使用打包脚本（PyInstaller，单文件 + windowed）
uv run python build.py

# 或手动
uv run pyinstaller MBForge.spec
# 输出在 dist/MBForge.exe
```

---

## 5. 测试指令

```bash
# 运行全部测试
uv run pytest tests/ -v

# 运行指定模块
uv run pytest tests/unit/test_project.py -v

# 生成覆盖率报告
uv run pytest tests/ --cov=mbforge --cov-report=html
```

### 测试结构

- `tests/unit/`：针对 `core/`、`models/` 等模块的单元测试。
- `tests/parser_io/`：`parser_io` 子包的独立测试。
- `tests/conftest.py`：将 `src/` 插入 `sys.path` 最前，确保 import 解析正确。
- 测试类使用 `TestXxx` 命名，测试方法使用 `test_xxx` 命名。
- 使用 `tempfile.TemporaryDirectory()` 与 `tmp_path` 处理文件系统临时数据。

---

## 6. 代码风格规范

### 6.1 文件头与导入

- **每个 `.py` 文件第一行必须是**：
  ```python
  from __future__ import annotations
  ```
- 导入顺序（三段式）：
  1. 标准库（`json`, `pathlib`, `typing`）
  2. 第三方库（`chromadb`, `PyQt6`）
  3. 本地应用（`from .base import ...`, `from ..utils.config import ...`）

### 6.2 类型提示

- 使用 `typing` 模块中的泛型：`List`, `Dict`, `Optional`，而非内置 `list[]`、`dict[]`。
- 文件路径统一使用 `pathlib.Path`，不使用字符串。
- 公共类/函数必须有类型注解。

### 6.3 类成员顺序

```python
class MyClass:
    # 1. 类属性 / dataclass 字段
    DEFAULT_VALUE = "..."

    # 2. 构造方法
    def __init__(self, ...): ...

    # 3. 公共方法
    def public_method(self, ...): ...

    # 4. property
    @property
    def something(self): ...

    # 5. 私有方法（_ 前缀）
    def _private_method(self, ...): ...

    # 6. 魔术方法
    def __repr__(self): ...

    # 7. 静态/类方法
    @classmethod
    def from_dict(cls, data): ...
```

### 6.4 日志与输出

- **禁止直接使用 `print()`**。统一使用项目日志系统：
  ```python
  from mbforge.utils.logger import get_logger
  logger = get_logger(__name__)
  logger.info("操作完成")
  logger.debug("详细信息: %s", variable)
  ```
- 控制日志级别：`MBFORGE_LOG_LEVEL=DEBUG uv run mbforge gui`

### 6.5 注释与文档

- 模块级、公共类、公共函数使用中文 docstring。
- Args / Returns 说明使用 Google 风格（见现有代码示例）。

---

## 7. 配置系统

### 全局配置

存储路径由 `platformdirs` 决定：
- Windows: `%APPDATA%/MBForge/config.json`
- macOS: `~/Library/Application Support/MBForge/config.json`
- Linux: `~/.config/MBForge/config.json`

包含：LLM / Embedding / Rerank / VLM 的 provider、模型名、API Key、device 等。

### 项目配置

每个项目根目录的 `.mbforge/settings.json` 存储 `ProjectSettings`：
- `name`：项目名称
- `model_overrides`：覆盖全局模型配置
- `workflow_toggles`：各工作流开关

### 配置优先级

项目级配置 > 全局配置 > 环境变量 > 默认值。

### 环境变量

关键变量（详见 `.env.template`）：

| 变量 | 说明 |
|------|------|
| `MBFORGE_LLM_PROVIDER` | LLM 提供商 |
| `MBFORGE_LLM_BASE_URL` | API 地址 |
| `MBFORGE_LLM_API_KEY` | API 密钥 |
| `MBFORGE_LLM_MODEL` | 模型名 |
| `MBFORGE_EMBED_MODEL` | Embedding 模型 |
| `MBFORGE_RERANK_MODEL` | Rerank 模型 |
| `MBFORGE_LOG_LEVEL` | 日志级别 |
| `UNIPARSER_HOST` | UniParser 服务地址 |
| `UNIPARSER_API_KEY` | UniParser API 密钥 |

---

## 8. 安全注意事项

- **API Key 管理**：所有 API Key 仅通过 `.env` 文件或环境变量注入，不得硬编码到源码中。
- **全局配置路径**：`config.json` 存储在用户数据目录，注意权限设置。
- **项目级敏感数据**：`.mbforge/` 目录可能包含索引、向量数据、解析结果，建议将其加入 `.gitignore`（项目根目录已配置）。
- **日志安全**：日志文件位于用户数据目录的 `logs/` 下，默认 rotates，避免敏感信息长期留存。
- **打包安全**：`build.py` 与 `MBForge.spec` 收集大量隐藏导入（`chromadb`, `sentence_transformers`, `rdkit` 等），修改打包逻辑时需验证运行时是否缺包。

---

## 9. 扩展点（供 Agent 参考）

### 添加新 LLM 提供商
1. 在 `models/` 新建模块，继承 `BaseLLM`。
2. 实现 `chat()`、`chat_stream()`、`achat()`、`achat_stream()`。
3. 在 `create_llm_from_config()` 中添加分发逻辑。

### 添加新 Agent 工具
1. 在 `agent/tools.py` 中定义工具函数，使用 `@tool` 装饰器。
2. 在 `agent/executor.py` 中注册：`self.registry.register(tools.my_tool)`。
3. 工具 schema 通过 `to_openai_schemas()` 自动导出。

### 添加工作流模块
1. 在 `workflow/` 创建模块，继承 `WorkflowBase`。
2. 在 `ProjectSettings` 中添加 toggle。
3. 在 UI 中接入开关。

---

## 10. 文档索引

项目内已有详尽的人类/开发者文档，Agent 在修改相关模块时应同步查阅或更新：

- `docs/ARCHITECTURE.md` — 系统架构与数据流
- `docs/API.md` — 公共 API 详细说明
- `docs/TECH_STACK.md` — 技术选型与版本约束
- `docs/DEVELOPMENT.md` — 完整开发指南（含分支命名、Commit 规范、PR 流程）
- `README.md` — 项目简介与快速开始
- `REFERENCES.md` — 引用文献

---

## 11. 提交与贡献规范

- **分支命名**：`feature/xxx`, `fix/xxx`, `refactor/xxx`, `docs/xxx`
- **Commit Message**：遵循 Conventional Commits
  ```
  feat: add substructure search tool
  fix: correct SMILES parsing for aromatic rings
  test: add KnowledgeBase search tests
  ```
- **PR 前检查**：
  ```bash
  uv run ruff format src/ && uv run ruff check src/ && uv run mypy src/ && uv run pytest tests/ -v
  ```
