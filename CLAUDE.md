# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What MBForge Is

PyQt6 桌面应用，用于分子科学/药物发现研究。核心流程：PDF 解析 → 分子提取 → 向量知识库构建 → AI Agent 对话查询。

## Build / Test / Lint Commands

```bash
# 安装依赖（uv workspace，包含 openSAR 和 UniParser-Tools）
uv sync --dev

# 启动 GUI
mbforge
# 或
uv run mbforge gui

# 新建项目
mbforge init ./my-project --name "MyProject"

# 索引项目 PDF
mbforge index ./my-project

# 运行测试
uv run pytest tests/ -v

# 运行单个测试文件
uv run pytest tests/unit/test_project.py -v

# 格式化
uv run ruff format src/

# Lint
uv run ruff check src/

# 打包 EXE
uv run python build.py
```

## Architecture

### Data Flow (Central Pipeline)

```
PDF → DocumentProcessor (PyMuPDF text/image)
  → MoleculeExtractor (regex + LLM SMILES extraction)
  → DocumentSummarizer (L0/L1/L2 layered summaries via LLM)
  → KnowledgeBase (ChromaDB vector store)
  → MoleculeDatabase (SQLite + RDKit, auto-computed properties)
```

This pipeline is `PDFParserPipeline` in `src/mbforge/parsers/pdf_parser.py`, invoked by both CLI `index` command and GUI `IndexWorker`.

### Module Layout

| 包 | 职责 | 关键类 |
|---|---|---|
| `core/` | 数据模型 | `Project`（vault 隐喻，`.mbforge/` 隐藏目录）、`KnowledgeBase`（ChromaDB 封装 + rerank）、`MoleculeDatabase`（SQLite + FTS5）、`DocumentProcessor`、`DocumentSummarizer` |
| `models/` | AI 模型抽象层 | `BaseLLM`/`BaseEmbedder`/`BaseReranker`/`BaseVLM` 基类 + `OpenAILLM`/`AnthropicLLM`/`SentenceTransformerEmbedder`。`create_llm_from_config()` 按 provider 字符串分发 |
| `parsers/` | PDF 解析与分子提取 | `PDFParserPipeline` 串联全部解析步骤 |
| `ui/` | PyQt6 界面 | `MainWindow`（主窗口，组装所有组件）、`ChatWidget`、`PDFViewer`（虚拟滚动 + 多线程渲染）、`MolPanel`、`FileTree` 等 |
| `agent/` | ReAct 循环 Agent | `ProjectAgent` + `LayeredContext` + `ToolExecutor`（10 个工具）+ `MemoryManager` + `TrajectoryTracker` |
| `workflow/` | 占位模块 | `generation`、`docking`、`qsar`、`md` — 仅 toggle 开关，尚未实现 |
| `parser_io/` | UniParser API 封装 | `ParserClient` 对接 `UniParser-Tools`，`ParseResult` 数据模型 |
| `utils/` | 配置、日志、辅助 | `AppConfig`、`get_logger`、`generate_uuid`、`split_text_chunks` |
| `sar/` | SAR 分析引擎 | `SARAnalyzer`（结构-活性关系分析） |
| `csar_io/` | 分子文件 I/O | `MoleculeReader`、`MoleculeWriter`，支持 CAS 查询 |
| `csar_vis/` | SAR 可视化 | `SARRenderer`、`PlotSettings` |
| `clustering/` | 分子聚类 | `MolecularClusterer`（指纹相似度）、`ScaffoldClusterer`（Bemis-Murcko） |
| `mcs/` | 最大公共子结构 | `MCSFinder` |
| `molecules/` | 分子数据模型 | `MoleculeEntry`、`MoleculeBatch`、`MoleculeDescriptorCalculator`、`LipinskiFilter`、`VeberFilter`、`PAINSFilter`、`MoleculeStandardizer`、`ScaffoldAnalyzer`、`RECAPFragmenter`、`BRICSFragmenter`、`SubstructureMatcher` |
| `csar_main.py` | CSAR CLI 入口 | `main()`，提供完整 SAR 分析工作流命令行接口（`uv run csar`） |

### Workspace Layout

```
MBForge/                  # uv workspace root
├── src/mbforge/          # 主应用（含合并后的 csar 代码）
├── setup/                # 一键配置脚本
└── tests/
```

`openSAR` 和 `UniParser-Tools` 位于 `setup/` 目录，作为 uv workspace 成员安装。当前核心代码直接用本地 PyMuPDF，未接入 UniParser API。openSAR 尚未集成到 mbforge 核心模块中。

### Config System (Two Tiers)

- **全局**: `~/.config/MBForge/config.json`（`AppConfig`）— LLM、embedding、rerank、VLM 设置，支持 `MBFORGE_LLM_*` 环境变量覆盖
- **项目级**: `.mbforge/settings.json`（`ProjectSettings`）— 模型覆盖、workflow toggle

### AI Model Layer

`src/mbforge/models/` 提供统一抽象。实现类：`OpenAILLM`（OpenAI 兼容 API）、`AnthropicLLM`、`SentenceTransformerEmbedder`、`APIEmbedder`、`SentenceTransformerReranker`、`APIVLM`。工厂函数 `create_llm_from_config()` 根据配置中的 provider 字段选择实现。

## Environment

```bash
cp .env.template .env
# 编辑 UNIPARSER_HOST、UNIPARSER_API_KEY 等
```

`pyproject.toml` 中 `[tool.uv]` 使用清华镜像源，并 override 了 pandas/numpy 版本约束。

## Key Files

| 文件 | 作用 |
|------|------|
| `src/mbforge/cli.py` | CLI 入口，`mbforge` 命令行工具 |
| `src/mbforge/app.py` | GUI 入口，`run_app()` 启动 PyQt6 主循环 |
| `src/mbforge/core/project.py` | `Project` 类管理 vault 元数据 |
| `src/mbforge/parsers/pdf_parser.py` | `PDFParserPipeline` 解析流水线 |
| `src/mbforge/agent/agent.py` | `ProjectAgent` ReAct 循环 |
| `src/mbforge/agent/tools.py` | Agent 可调用的 10 个工具定义 |

## Code Patterns

### Adding a new tool to Agent

1. Define tool in `src/mbforge/agent/tools.py` using `@tool` decorator
2. Register in `ToolExecutor.registry` in `agent/executor.py`
3. Tool schema exported via `registry.to_openai_schemas()` for function calling

### Adding a new model provider

1. Inherit `BaseLLM` in `src/mbforge/models/`
2. Add provider dispatch in `create_llm_from_config()` in `models/llm.py`

### Adding a new workflow module

1. Create module under `src/mbforge/workflow/`
2. Inherit `WorkflowBase` from `workflow/base.py`
3. Add toggle in `ProjectSettings` and UI toggle in `ui/`

## Development Rules

### 遇到报错时
停下来描述：(1) 错误现象 (2) 理解 (3) 解决方案，再行动。不要盲目穷举。

## Code Navigation (CodeGraph)

Use `codegraph` CLI for code navigation and impact analysis:

```bash
codegraph query "SymbolName"     # 符号搜索，含类型签名和行号
codegraph callers "func_name"    # 追踪调用者
codegraph callees "func_name"    # 被调用分析
codegraph impact "ClassName"     # 重构前影响范围评估
codegraph context "自然语言描述"  # AI 上下文构建
codegraph sync                   # 代码修改后同步索引
```

索引状态：122 文件 / 2,363 节点 / 4,824 边。重构前必查 impact。

