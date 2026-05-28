# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What MBForge Is

React+Vite+Tauri 桌面应用，用于分子科学/药物发现研究。核心流程：PDF 解析 → 分子提取 → 向量知识库构建 → AI Agent 对话查询。FastAPI 模型服务器提供后端 API，React 前端通过 Tauri 桥接调用。

## Build / Test / Lint Commands

```bash
# 安装 Python 依赖（uv workspace，包含 openSAR 和 UniParser-Tools）
uv sync --dev

# 安装前端依赖
cd frontend && npm install

# 启动前端开发服务器（Vite, port 5173）
cd frontend && npm run dev

# 启动模型服务器（FastAPI, port 18792）
uv run uvicorn mbforge.model_server.main:app --host 127.0.0.1 --port 18792

# 启动 GUI（自动启动模型服务器 + 打开浏览器）
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

# 前端构建
cd frontend && npm run build

# 打包 EXE（Tauri）
cd src-tauri && cargo tauri build
```

## Architecture

### Data Flow (Central Pipeline)

```
PDF → pdf-inspector (Rust Tauri command) → Markdown + classification
  ↓ (fallback: PyMuPDF + PDFClassifier)
  → split_text_chunks()
  → MoleculeExtractor (regex SMILES) or MolImagePipeline (YOLO detection)
  → DocumentSummarizer (L0/L1/L2 layered summaries via LLM)
  → KnowledgeBase.index_document() (ChromaDB vector store)
```

This pipeline is `PDFParserPipeline` in `src/mbforge/parsers/pdf_parser.py`, invoked by both CLI `index` command and model server endpoints.

### pdf-inspector Integration

pdf-inspector (Rust) is integrated as Tauri commands for PDF classification and text extraction:
- `classify_pdf`: PDF type classification (TextBased/Scanned/Mixed/ImageBased), ~10-50ms
- `extract_text`: Structured Markdown extraction with tables, headings, lists
- Python pipeline calls Tauri commands via HTTP (transition period), falls back to PyMuPDF when unavailable
- Config: `OcrConfig.use_pdf_inspector` (default: True)
- Rust source: `src-tauri/src/commands/pdf.rs`
- Frontend bridge: `frontend/src/api/tauri-bridge.ts`

### System Architecture

```
┌─────────────────────┐     ┌─────────────────────────┐
│  React+Vite Frontend │────▶│  FastAPI Model Server    │
│  (port 5173)         │     │  (port 18792)            │
│  Vite proxy /api/v1  │     │  13 routers under        │
│  → localhost:18792   │     │  /api/v1/*               │
└─────────────────────┘     └─────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
             ┌──────────┐    ┌──────────┐    ┌──────────┐
             │ PDFParser │    │ Agent    │    │ Knowledge│
             │ Pipeline  │    │ (ReAct)  │    │ Base     │
             └──────────┘    └──────────┘    └──────────┘
```

**Dev mode**: Vite dev server proxies `/api/v1/*` to `localhost:18792`. The model server must be running separately (`uv run uvicorn`).
**Production**: Tauri shell spawns uvicorn as a sidecar process on app launch, kills it on close.

### Module Layout

| 包 | 职责 | 关键类 |
|---|---|---|
| `core/` | 数据模型 | `Project`（vault 隐喻，`.mbforge/` 隐藏目录）、`KnowledgeBase`（ChromaDB 封装 + rerank）、`MoleculeDatabase`（SQLite + FTS5）、`DocumentProcessor`、`DocumentSummarizer` |
| `models/` | AI 模型抽象层 | `BaseLLM`/`BaseEmbedder`/`BaseReranker`/`BaseVLM` 基类 + `OpenAILLM`/`AnthropicLLM`/`SentenceTransformerEmbedder`。`create_llm_from_config()` 按 provider 字符串分发 |
| `parsers/` | PDF 解析与分子提取 | `PDFParserPipeline` 串联全部解析步骤 |
| `model_server/` | FastAPI 模型服务器 | 路由：`llm`、`embed`、`rerank`、`vlm`、`agent`、`kb`、`molecule`、`moldet`、`uniparser`、`project`、`file`、`health` |
| `agent/` | ReAct 循环 Agent | `ProjectAgent` + `LayeredContext` + `ToolExecutor`（10 个工具）+ `MemoryManager` + `TrajectoryTracker` |
| `plugins/` | 插件系统 | `PluginBase`、`PluginRegistry`，含 `cadd_template` 和 `unidock` 插件 |
| `workflow/` | 占位模块 | `generation`、`docking`、`qsar`、`md` — 仅 toggle 开关，尚未实现 |
| `parsers/uniparser/` | UniParser API 封装 | `ParserClient` 对接 `UniParser-Tools`，`ParseResult` 数据模型 |
| `utils/` | 配置、日志、辅助 | `AppConfig`、`get_logger`、`generate_uuid`、`split_text_chunks` |
| `sar/` | SAR 分析引擎 | `SARAnalyzer`（结构-活性关系分析） |
| `csar_io/` | 分子文件 I/O | `MoleculeReader`、`MoleculeWriter`，支持 CAS 查询 |
| `csar_vis/` | SAR 可视化 | `SARRenderer`、`PlotSettings` |
| `clustering/` | 分子聚类 | `MolecularClusterer`（指纹相似度）、`ScaffoldClusterer`（Bemis-Murcko） |
| `mcs/` | 最大公共子结构 | `MCSFinder` |
| `molecules/` | 分子数据模型 | `MoleculeEntry`、`MoleculeBatch`、`MoleculeDescriptorCalculator`、`LipinskiFilter`、`VeberFilter`、`PAINSFilter`、`MoleculeStandardizer`、`ScaffoldAnalyzer`、`RECAPFragmenter`、`BRICSFragmenter`、`SubstructureMatcher` |
| `csar_main.py` | CSAR CLI 入口 | `main()`，提供完整 SAR 分析工作流命令行接口（`uv run csar`） |
| `frontend/` | React+Vite 前端 | `App.tsx`（路由）、组件：`Chat`、`PDFViewer`、`MoleculeLibrary`、`Workflow`、`Settings`、`Search`、`ProjectView` |
| `src-tauri/` | Tauri 桥接层 | `main.rs`（Rust 入口）、`tauri.conf.json`（窗口配置） |

### Workspace Layout

```
MBForge/                  # uv workspace root
├── src/mbforge/          # 主应用（含合并后的 csar 代码）
├── frontend/             # React+Vite 前端
├── src-tauri/            # Tauri Rust 桥接层
├── setup/                # 一键配置脚本
└── tests/
```

`openSAR` 和 `UniParser-Tools` 位于 `setup/` 目录，作为 uv workspace 成员安装。当前核心代码直接用本地 PyMuPDF，未接入 UniParser API。openSAR 尚未集成到 mbforge 核心模块中。

### Config System (Two Tiers)

- **全局**: `~/.config/MBForge/config.json`（`AppConfig`）— LLM、embedding、rerank、VLM 设置，支持 `MBFORGE_LLM_*` 环境变量覆盖
- **项目级**: `.mbforge/settings.json`（`ProjectSettings`）— 模型覆盖、workflow toggle

### AI Model Layer

`src/mbforge/models/` 提供统一抽象。实现类：`OpenAILLM`（OpenAI 兼容 API）、`AnthropicLLM`、`SentenceTransformerEmbedder`、`APIEmbedder`、`SentenceTransformerReranker`、`APIVLM`。工厂函数 `create_llm_from_config()` 根据配置中的 provider 字段选择实现。

### Model Server API

FastAPI 服务器运行在 `127.0.0.1:18792`，提供以下端点：

| 端点前缀 | 功能 |
|----------|------|
| `/api/v1/llm` | LLM 推理（chat/stream） |
| `/api/v1/embed` | 文本 Embedding |
| `/api/v1/rerank` | 结果重排序 |
| `/api/v1/vlm` | 视觉语言模型 |
| `/api/v1/agent` | Agent 对话（chat/chat-stream） |
| `/api/v1/kb` | 知识库管理 |
| `/api/v1/molecule` | 分子数据库查询 |
| `/api/v1/moldet` | 分子图像检测 |
| `/api/v1/uniparser` | PDF 解析代理 |
| `/api/v1/project` | 项目管理 |
| `/api/v1/file` | 文件操作 |
| `/api/v1/settings` | 设置管理 |
| `/api/v1/health` | 健康检查 |

### Agent Manager (Singleton)

`src/mbforge/model_server/agent_manager.py` 管理全局单例 `ProjectAgent`。切换项目时调用 `switch_project()` 保存旧上下文、加载新项目的 KB + mol_db + ToolExecutor。聊天历史持久化到 `.mbforge/memory/chat_history.json`。

## Environment

```bash
cp .env.template .env
# 编辑 UNIPARSER_HOST、UNIPARSER_API_KEY 等
```

`pyproject.toml` 中 `[tool.uv]` 使用清华镜像源，PyTorch 使用 `pytorch-cu128` 索引（CUDA 12.8），并 override 了 pandas/numpy 版本约束。

## Frontend Development

`frontend/vite.config.ts` 配置了 API 代理：`/api/v1` → `http://localhost:18792`。开发时需同时运行前端和后端：

```bash
# 终端 1：模型服务器
uv run uvicorn mbforge.model_server.main:app --host 127.0.0.1 --port 18792

# 终端 2：前端
cd frontend && npm run dev
```

## Key Files

| 文件 | 作用 |
|------|------|
| `src/mbforge/cli.py` | CLI 入口，`mbforge` 命令行工具 |
| `src/mbforge/model_server/main.py` | FastAPI 模型服务器入口 |
| `src/mbforge/model_server/agent_manager.py` | Agent 单例管理，项目切换，聊天历史持久化 |
| `src/mbforge/core/project.py` | `Project` 类管理 vault 元数据 |
| `src/mbforge/parsers/pdf_parser.py` | `PDFParserPipeline` 解析流水线 |
| `src/mbforge/agent/agent.py` | `ProjectAgent` ReAct 循环 |
| `src/mbforge/agent/tools.py` | Agent 可调用的 10 个工具定义 |
| `frontend/src/App.tsx` | React 前端路由入口 |
| `frontend/vite.config.ts` | Vite 配置（API 代理到 18792） |
| `src-tauri/src/main.rs` | Tauri 桥接层 Rust 入口 |

## Code Patterns

### Adding a new API endpoint to Model Server

1. Create router in `src/mbforge/model_server/routers/` using `APIRouter`
2. Add dependency injection in `src/mbforge/model_server/dependencies.py` if needed
3. Register in `src/mbforge/model_server/main.py` via `app.include_router()`
4. If it needs model singletons, use `get_llm()` etc. from `src/mbforge/model_server/models/`

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
3. Add toggle in `ProjectSettings`

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
