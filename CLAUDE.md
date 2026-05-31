# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What MBForge Is

React+Vite+Tauri 桌面应用，用于分子科学/药物发现研究。双语言架构：
- **Rust** (`src-tauri/src/`): Agent ReAct 循环、PDF 原生解析（lopdf）、分子 SQLite 数据库、Tauri 命令层 — ~9,700 行
- **Python** (`src/mbforge/`): FastAPI 模型服务器（port 18792）、LLM/Embedding/VLM 推理、ChromaDB 向量库、MolScribe — ~12,900 行

核心流程：PDF 解析 → 分子提取 → 向量知识库构建 → AI Agent 对话查询。

## Build / Test / Lint Commands

```bash
# Rust 编译检查
cd src-tauri && cargo check

# Rust 测试（99 个）
cd src-tauri && cargo test

# 安装 Python 依赖
uv sync --dev

# 安装前端依赖
cd frontend && npm install

# 启动前端开发服务器（Vite, port 5173）
cd frontend && npm run dev

# 启动模型服务器（FastAPI, port 18792）
uv run uvicorn mbforge.model_server.main:app --host 127.0.0.1 --port 18792

# Python 测试（28 个）
uv run pytest tests/ -v

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

### System Architecture

```
┌────────────────────────────────────────────────────────┐
│  React + Vite + TypeScript  (port 5173)                 │
│  ┌──────────┐ ┌──────────┐ ┌─────────────────────────┐ │
│  │  Chat     │ │Molecule  │ │ Settings / Project View │ │
│  │  UI       │ │ Library  │ │                         │ │
│  └────┬─────┘ └────┬─────┘ └───────────┬─────────────┘ │
│       │            │                    │               │
│  ┌────┴────────────┴────────────────────┴──────────┐   │
│  │   tauri-bridge.ts  (window.__TAURI__.invoke)     │   │
│  └───────────────────────┬──────────────────────────┘   │
└──────────────────────────┼──────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────┐
│  Tauri v2 Shell          │                               │
│  ┌───────────────────────┴─────────────────────────┐    │
│  │  Rust Agent + Parsers (src-tauri/src/)           │    │
│  │                                                   │    │
│  │  commands/ (6)  core/ (16)  parsers/ (12)        │    │
│  │  │              │              │                  │    │
│  │  │  Tauri API   │  ReAct Loop  │  PDF Pipeline    │    │
│  │  │  invoke →    │  LLM+Tools+  │  lopdf +         │    │
│  │  │  JSON        │  Memory+     │  MinerU+         │    │
│  │  │              │  Trajectory  │  LlamaParse+     │    │
│  │  └──────────────┴──────────────┴──────────────────┘    │
│  ┌──────────────────────────────────────────────────┐    │
│  │  FastAPI Sidecar (port 18792, spawned by Tauri)  │    │
│  │  routers/ (15)  models/  agents/  parsers/       │    │
│  │  LLM / Embed / Rerank / VLM / KB / MolScribe    │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

**Dev mode**: Vite dev server proxies `/api/v1/*` to `localhost:18792` + `window.__TAURI__.invoke()` for Rust commands.
**Production**: Tauri shell spawns uvicorn as sidecar. Frontend uses both HTTP API and Tauri invoke.

### Data Flow (Central Pipeline)

```
PDF ─→ Rust parsers/pipeline.rs (Stage 1-6)
  │
  ├─ 1. classify: intent.rs → PDF type / structure
  ├─ 2. extract:  mineru.rs / llama_parse.rs / uniparser.rs → Markdown
  ├─ 3. images:   images.rs (lopdf) → embedded images
  ├─ 4. associate: association.rs + keywords.rs → molecules + activities
  ├─ 5. pending:  pending.rs → save partial results
  └─ 6. store:    molecule_store.rs → SQLite + FTS5
       │
       └─→ Python side: LLM post_process → StructuredData → KnowledgeBase (ChromaDB)
```

Python fallback: `PDFParserPipeline` in `src/mbforge/parsers/pdf_parser.py` (PyMuPDF) is used when Rust pipeline is unavailable (CLI `index` command).

### Module Layout

#### Rust 侧 — `src-tauri/src/` (9,681 行 / ~34 模块)

| 模块 | 文件数 | 职责 | 关键类型 |
|------|--------|------|----------|
| `commands/` | 6 | Tauri invoke 命令层 | `classify_pdf`, `extract_text`, `extract_smiles`, `mol_init`, `agent_init` 等 25+ 命令 |
| `core/` | 16 | Agent + 数据层 | `Agent` (ReAct), `LlmClient`, `LayeredContext`, `ToolExecutor`, `MoleculeRecord`, `MoleculeDatabase`, `MemoryManager`, `TrajectoryTracker` |
| `parsers/` | 12 | PDF 解析管线 | `PdfParseResult` (pipeline), `ExtractionResult` (association), `ExtractedImage`, `MineruClient`, `UniParserClient` |

#### Python 侧 — `src/mbforge/` (12,882 行)

| 模块 | 职责 | 关键类 |
|------|------|--------|
| `core/` | 数据模型 | `Project`, `KnowledgeBase` (ChromaDB), `MoleculeDatabase` (SQLite+FTS5), `DocumentSummarizer` |
| `models/` | AI 模型 | `BaseLLM`/`OpenAILLM`/`AnthropicLLM`, `SentenceTransformerEmbedder`, `BaseVLM` |
| `model_server/` | FastAPI 服务 | 15 routers, singleton managers for LLM/Embed/Rerank/VLM/MolDet |
| `parsers/` | Python 解析 | `PDFParserPipeline`, `MoleculeExtractor`, `MolImagePipeline`, `MolScribe` |
| `agent/` | 工具框架 | `ToolExecutor` (10 tools), semantic cache, streaming search |
| `molecules/` | 数据合约 | `MoleculeEntry`, `MoleculeBatch` schema |

### Rust Agent (Primary)

`src-tauri/src/core/agent.rs` 实现完整的 ReAct Agent：
- `Agent::new()` — 初始化 LLM client + ToolExecutor + context
- `Agent::chat()` / `Agent::chat_stream()` — 循环：LLM 调用 → 工具执行 → 结果注入
- `Agent::switch_project()` — 切换项目上下文
- 20+ 工具注册在 `core/executor.rs`，含 KB 搜索、分子查询、SAR、文件操作、Agent 子代理
- 记忆系统：`MemoryManager`（6 分类持久化）+ `TrajectoryTracker`（500 steps）
- Python 模型服务器通过 `model_server/agent_manager.py` 桥接调用

### Config System (Two Tiers)

- **全局**: `~/.config/MBForge/config.json`（`AppConfig`）— LLM、embedding、rerank、VLM 设置
- **项目级**: `.mbforge/settings.json`（`ProjectSettings`）— 模型覆盖、workflow toggle

### Model Server API

| 端点前缀 | 功能 |
|----------|------|
| `/api/v1/llm` | LLM 推理（chat/stream） |
| `/api/v1/embed` | 文本 Embedding |
| `/api/v1/rerank` | 结果重排序 |
| `/api/v1/vlm` | 视觉语言模型 + MolScribe |
| `/api/v1/agent` | Agent 桥接（chat/chat-stream） |
| `/api/v1/kb` | 知识库管理 |
| `/api/v1/molecule` | 分子数据库查询 |
| `/api/v1/moldet` | 分子图像检测 |
| `/api/v1/uniparser` | PDF 解析代理 |
| `/api/v1/project` | 项目管理 |
| `/api/v1/file` | 文件操作 |
| `/api/v1/settings` | 设置管理 |
| `/api/v1/health` | 健康检查 |
| `/api/v1/download` | 模型下载（ModelScope） |
| `/api/v1/chem` | 化学操作 |

### Phase 1–3 Migration Status

PDF 解析 Python→Rust 迁移进展：

| Phase | 内容 | 状态 |
|-------|------|------|
| 1.1 | SMILES 提取 + 关联提取命令 | ✅ 完成 |
| 1.2 | 分子-文本关联引擎 | ✅ 完成 |
| 1.3 | 关键词 & 实体提取 | ✅ 完成 |
| 1.4 | 文档摘要持久化 | ✅ 完成 |
| 1.5 | 待处理提取保存 | ✅ 完成 |
| 2 | SQLite 分子数据库（FTS5 + 属性估算） | ✅ 完成 |
| 3 | 图像提取（lopdf 嵌入式 XObject） | ✅ 完成 |
| 4 | OCR 集成（LiteParse + PDFium） | ✅ 完成 |
| 5 | VLM 描述管线 | ✅ 完成（Python sidecar） |
| 6 | 内容提取 + 关联 | ✅ 完成 |

## Key Files

| 文件 | 作用 |
|------|------|
| `src-tauri/src/main.rs` | Tauri 入口，25+ 命令注册，uvicorn sidecar 管理 |
| `src-tauri/src/core/agent.rs` | **Rust ReAct Agent** 核心循环 |
| `src-tauri/src/core/llm.rs` | LLM HTTP 客户端（OpenAI/Anthropic 兼容） |
| `src-tauri/src/core/executor.rs` | 20+ 工具注册器 |
| `src-tauri/src/core/molecule_store.rs` | SQLite 分子数据库 + FTS5 + 属性估算 |
| `src-tauri/src/parsers/pipeline.rs` | 统一 PDF 解析管线（Stage 1-6） |
| `src-tauri/src/parsers/images.rs` | lopdf 图像提取 |
| `src-tauri/src/parsers/association.rs` | 分子-文本关联引擎 |
| `src-tauri/src/commands/molecule.rs` | 18 个分子数据库 Tauri 命令 |
| `src-tauri/src/commands/agent.rs` | Agent 会话 Tauri 命令 |
| `src/mbforge/model_server/main.py` | FastAPI 模型服务器入口 |
| `src/mbforge/core/knowledge_base.py` | ChromaDB 向量知识库 |
| `frontend/src/App.tsx` | React 前端路由入口 |
| `frontend/src/api/tauri-bridge.ts` | Tauri invoke 桥接 |

## Code Patterns

### Adding a new Rust Tauri command

```rust
// 1. 在 commands/ 下某模块定义命令
#[tauri::command]
pub fn my_command(arg: String) -> Result<String, String> {
    Ok(format!("processed: {}", arg))
}

// 2. 在 main.rs 中注册
app.invoke_handler(tauri::generate_handler![
    commands::my_command,
    // ...
]);
```

### Adding a new Rust Agent tool

```rust
// 1. 在 core/executor.rs 注册 ToolInfo
ToolInfo {
    name: "my_tool",
    description: "Description for LLM",
    parameters: serde_json::json!({
        "type": "object",
        "properties": { "arg": { "type": "string" } },
        "required": ["arg"],
    }),
}

// 2. 在 core/executor.rs 添加执行逻辑
"my_tool" => {
    let arg = args.get("arg").and_then(|v| v.as_str()).unwrap_or("");
    // 执行...
    Ok(serde_json::json!({ "result": arg }))
}
```

### Adding a new API endpoint to Model Server

1. Create router in `src/mbforge/model_server/routers/` using `APIRouter`
2. Register in `main.py` via `app.include_router()`

### Adding a new PDF parser backend

1. Create client in `src-tauri/src/parsers/` (e.g., `myparser.rs`)
2. Implement `async fn parse(&self, input: &str) -> Result<ParsedOutput, String>`
3. Add variant in `pipeline.rs` parser selection logic

### 遇到报错时

停下来描述：(1) 错误现象 (2) 理解 (3) 解决方案，再行动。不要盲目穷举。

## Built-in Documentation

| 文档 | 位置 |
|------|------|
| E-SMILES 规范 + MBForge 集成 | `src-tauri/docs/esmiles/` |
| LiteParse API 参考（官网存档） | `src-tauri/docs/liteparse/` |
| 项目系统架构 | `docs/ARCHITECTURE.md` |
| 公共 API 参考 | `docs/API.md` |
| 技术栈详情 | `docs/TECH_STACK.md` |
| 开发指南 | `docs/DEVELOPMENT.md` |
| Agent 工作规范 | `AGENTS.md` || PDF 迁移规划 | `docs/pipeline-migration-plan.md` |
| 管线重设计 | `docs/pipeline-redesign.md` |
| PDF 提取工作流 | `docs/pdf-extraction-workflow.md` |

