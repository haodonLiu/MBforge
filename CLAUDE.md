# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What MBForge Is

React+Vite+Tauri 桌面应用，用于分子科学/药物发现研究。双语言架构：
- **Rust** (`src-tauri/src/`): Agent ReAct 循环、PDF 原生解析（lopdf）、分子 SQLite 数据库、Tauri 命令层
- **Python** (`src/mbforge/`): FastAPI 模型服务器（port 18792）、LLM/Embedding/VLM 推理、MolScribe

核心流程：PDF 解析 → 分子提取 → 向量知识库构建 → AI Agent 对话查询。
不允许任何基于假设或者推测的代码出现
## Build / Test / Lint Commands

```bash
# Rust 编译检查
cd src-tauri && cargo check

# Rust 测试（~226 个）
cd src-tauri && cargo test

# 安装 Python 依赖
uv sync --dev

# 安装前端依赖
cd frontend && npm install

# 启动前端开发服务器（Vite, port 5173）
cd frontend && npm run dev

# 启动模型服务器（FastAPI, port 18792）
uv run uvicorn mbforge.model_server.main:app --host 127.0.0.1 --port 18792

# Python 测试（83 个）
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
│  │  commands/ (12) core/ (32)  parsers/ (20)        │    │
│  │  │              │              │                  │    │
│  │  │  Tauri API   │  ReAct Loop  │  PDF Pipeline    │    │
│  │  │  invoke →    │  LLM+Tools+  │  lopdf +         │    │
│  │  │  JSON        │  Memory+     │  MinerU+         │    │
│  │  │              │  Trajectory  │  LlamaParse+     │    │
│  │  └──────────────┴──────────────┴──────────────────┘    │
│  ┌──────────────────────────────────────────────────┐    │
│  │  FastAPI Sidecar (port 18792, spawned by Tauri)  │    │
│  │  routers/ (16)  models/  parsers/  molecules/    │    │
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
  ├─ 6. store:    molecule_store.rs → SQLite + FTS5
  ├─ 2c. images:  vlm_chem.rs → describe_image_cached (非化学结构图 VLM 描述)
  ├─ 3.5. chem:   chem_validate.rs → batch validate → confidence 降级
  └─ 7. report:   report.rs + knowledge_base.rs
       │
        └─→ Python side: LLM post_process → StructuredData → KnowledgeBase (FTS5 + semantic_cache)
```

Python fallback: `PDFParserPipeline` in `src/mbforge/parsers/pdf_parser.py` (PyMuPDF) is used when Rust pipeline is unavailable (CLI `index` command).

### Adding a new Rust Agent tool

```rust
// 1. 在 core/executor/ 的 `ToolExecutor::tools()` 注册 ToolInfo
ToolInfo {
    name: "my_tool",
    description: "Description for LLM",
    parameters: serde_json::json!({
        "type": "object",
        "properties": { "arg": { "type": "string" } },
        "required": ["arg"],
    }),
}

// 2. 在 core/executor/mod.rs 的 `execute()` 匹配分支中添加逻辑
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

### 每次任务后的文档更新

完成任何代码修改后，必须在 **CODEMAP.md §7.6 待审核事项** 中记录修改内容（日期、文件、问题描述、状态 `⚠️ 待审核`），由人工确认后标记 ✅。


## Built-in Documentation

| 文档 | 位置 |
|------|------|
| Agent 工作规范 | `AGENTS.md` |
| 代码逻辑树（最详细） | `CODEMAP.md` |
| 技术栈详情 | `docs/TECH_STACK.md` |
| 第三方引用 | `docs/REFERENCES.md` |
| PDF 迁移规划 | `docs/pipeline-migration-plan.md` |
| 管线重设计 | `docs/pipeline-redesign.md` |
| PDF 提取工作流 | `docs/pdf-extraction-workflow.md` |
| 开发规范集 | `docs/specs/` | 架构约定、代码风格、分子表示 |
| E-SMILES 规范 | `src-tauri/docs/esmiles/` |
| LiteParse API 参考 | `src-tauri/docs/liteparse/` |

