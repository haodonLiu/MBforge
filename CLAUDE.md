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

| 包 | 职责 |
|---|---|
| `core/` | 数据模型：`Project`（vault 隐喻，`.mbforge/` 隐藏目录）、`KnowledgeBase`（ChromaDB 封装 + rerank）、`MoleculeDatabase`（SQLite + FTS5）、`DocumentProcessor`、`DocumentSummarizer` |
| `models/` | AI 模型抽象层：`BaseLLM`/`BaseEmbedder`/`BaseReranker`/`BaseVLM` 基类 + OpenAI/Anthropic/本地实现。`create_llm_from_config()` 按 provider 字符串分发 |
| `parsers/` | PDF 解析与分子提取。`PDFParserPipeline` 串联全部解析步骤 |
| `ui/` | PyQt6 界面：`MainWindow`（主窗口，组装所有组件）、`ChatWidget`、`PDFViewer`、`MolPanel`、`FileTree` 等 |
| `agent/` | ReAct 循环 Agent：`ProjectAgent` + `LayeredContext` + `ToolExecutor`（10 个工具，OpenAI function-calling schema）+ `MemoryManager` + `TrajectoryTracker` |
| `workflow/` | 占位模块：`generation`、`docking`、`qsar`、`md` — 仅 toggle 开关，尚未实现 |
| `utils/` | 配置（`AppConfig`）、日志、常量、辅助函数 |

### Workspace Layout

```
MBForge/                  # uv workspace root
├── src/mbforge/          # 主应用
├── setup/                # 一键配置脚本 + 依赖组件
│   ├── openSAR/          # uv workspace member，装为 csar（SAR 分析工具箱）
│   └── UniParser-Tools/  # uv workspace member，装为 uniparser-tools（远程 PDF 解析 API）
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
