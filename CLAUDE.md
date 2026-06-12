# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

Tradeoff: These guidelines bias toward caution over speed. For trivial tasks, use judgment.

1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

State your assumptions explicitly. If uncertain, ask.
If multiple interpretations exist, present them - don't pick silently.
If a simpler approach exists, say so. Push back when warranted.
If something is unclear, stop. Name what's confusing. Ask.
2. Simplicity First
Minimum code that solves the problem. Nothing speculative.

No features beyond what was asked.
No abstractions for single-use code.
No "flexibility" or "configurability" that wasn't requested.
No error handling for impossible scenarios.
If you write 200 lines and it could be 50, rewrite it.
Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

3. Surgical Changes
Touch only what you must. Clean up only your own mess.

When editing existing code:

Don't "improve" adjacent code, comments, or formatting.
Don't refactor things that aren't broken.
Match existing style, even if you'd do it differently.
If you notice unrelated dead code, mention it - don't delete it.
When your changes create orphans:

Remove imports/variables/functions that YOUR changes made unused.
Don't remove pre-existing dead code unless asked.
The test: Every changed line should trace directly to the user's request.

4. Goal-Driven Execution
Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

"Add validation" → "Write tests for invalid inputs, then make them pass"
"Fix the bug" → "Write a test that reproduces it, then make it pass"
"Refactor X" → "Ensure tests pass before and after"
For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

These guidelines are working if: fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## What MBForge Is

React+Vite+Tauri 桌面应用，用于分子科学/药物发现研究。双语言架构：
- **Rust** (`src-tauri/src/`): Agent ReAct 循环、PDF 原生解析（lopdf）、分子 SQLite 数据库、Tauri 命令层、化学信息学（chematic crate）
- **Python** (`src/mbforge/`): FastAPI 模型服务器（port 18792）、Embedding、Rerank、MolDet、MolScribe

核心流程：PDF 解析 → 分子提取 → 向量知识库构建 → AI Agent 对话查询。
不允许任何基于假设或者推测的代码出现
## TODO
任务看板记录在 `TODO/INDEX.md`（根 `TODO.md` 已废弃，统一指向 `TODO/INDEX.md`），
## Build / Test / Lint Commands

```bash
# Rust 编译检查
cd src-tauri && cargo check

# Rust 测试
cd src-tauri && cargo test

# 安装 Python 依赖
uv sync --dev

# 安装前端依赖
cd frontend && npm install

# 启动前端开发服务器（Vite, port 5173）
cd frontend && npm run dev

# 启动模型服务器（FastAPI, port 18792）
uv run uvicorn mbforge.server:app --host 127.0.0.1 --port 18792

# Python 测试
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
│  │   api/tauri/*.ts  (window.__TAURI__.invoke)      │   │
│  └───────────────────────┬──────────────────────────┘   │
└──────────────────────────┼──────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────┐
│  Tauri v2 Shell          │                               │
│  ┌───────────────────────┴─────────────────────────┐    │
│  │  Rust Agent + Parsers (src-tauri/src/)           │    │
│  │                                                   │    │
│  │  commands/ (18) core/ (74)  parsers/ (27)        │    │
│  │  │              │              │                  │    │
│  │  │  Tauri API   │  ReAct Loop  │  PDF Pipeline    │    │
│  │  │  invoke →    │  LLM+Tools+  │  lopdf +         │    │
│  │  │  JSON        │  Memory+     │  MinerU+         │    │
│  │  │              │  Trajectory  │  LlamaParse+     │    │
│  │  └──────────────┴──────────────┴──────────────────┘    │
│  ┌──────────────────────────────────────────────────┐    │
│  │  FastAPI Sidecar (port 18792, spawned by Tauri)  │    │
│  │  backends/ (5)  server.py                        │    │
│  │  LLM / Embed / Rerank / VLM / KB / MolScribe    │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

**Dev mode**: Vite dev server proxies `/api/v1/*` to `localhost:18792` for sidecar health checks; all frontend business logic goes through `window.__TAURI__.invoke()`.
**Production**: Tauri shell spawns uvicorn as sidecar. Frontend communicates exclusively via Tauri IPC (Rust commands + events).

### Data Flow (Central Pipeline)

```
PDF ─→ Rust parsers/pipeline.rs (Stage 1-7)
  │
  ├─ 1. classify:   intent.rs → PDF type / structure
  ├─ 2. extract:    mineru.rs / llama_parse.rs / uniparser.rs → Markdown
  ├─ 3. images:     images.rs (lopdf) → embedded images
  ├─ 4. associate:  association.rs + keywords.rs → molecules + activities
  ├─ 5. pending:    ingest_queue.rs → save partial results
  ├─ 6. store:      molecule_store.rs → SQLite + FTS5
  ├─ 2c. vlm:       vlm_chem.rs → 化学结构图 VLM 识别 + SHA-256 缓存
  ├─ 3.5. validate: chem_validate.rs → batch validate → confidence 降级
  └─ 7. report:     report.rs + knowledge_base.rs
       │
        └─→ Python side: post_process → StructuredData → KnowledgeBase (FTS5 + semantic_cache)
```

### 分子三层表示

MBForge 使用三层分子表示，逐层可逆：

| 层级 | 格式 | 存储 | 用途 |
|------|------|------|------|
| Layer 1 | SMILES | `molecules.db` `smiles` 列 (NOT NULL) | RDKit 兼容、指纹计算、子结构搜索 |
| Layer 2 | E-SMILES | `molecules.db` `esmiles` 列 (nullable) | 语义标签（`<a>N:GROUP</a>`），Markush 结构 |
| Layer 3 | MoleCode | 运行时生成（不持久化） | LLM 推理用，Mermaid 图语法，显式拓扑 |

转换通路（纯 Rust，`core/esmiles.rs` + `core/molecode.rs`）：
- SMILES → E-SMILES：`smiles_to_esmiles(smiles, tags)` — 添加 `<sep>` + 标签
- E-SMILES → SMILES：`parse_esmiles_tags(esmiles)` — 取 `<sep>` 前的内容
- E-SMILES → MoleCode：`esmiles_to_molecode(esmiles, name)` — chematic 解析 → kekulize → Mermaid 文本

化学信息学使用 `chematic` crate（git: `kent-tokyo/chematic`），提供 SMILES 解析、ECFP4 指纹、Tanimoto 相似度、VF2 子结构匹配。

### Adding a new Rust Agent tool (rig-core)

```rust
// 1. 在 core/agent/executor_rig.rs 中声明 Tool + Args
#[derive(Deserialize, JsonSchema)]
pub struct MyToolArgs { pub arg: String }

#[derive(Clone)]
pub struct MyTool { pub project_root: String }

impl Tool for MyTool {
    const NAME: &'static str = "my_tool";
    type Error = ToolError;
    type Args = MyToolArgs;
    type Output = String;

    async fn definition(&self, _prompt: String) -> ToolDefinition {
        let schema = serde_json::to_value(schemars::schema_for!(MyToolArgs)).unwrap();
        ToolDefinition { name: Self::NAME.into(), description: "...".into(), parameters: schema }
    }

    async fn call(&self, args: Self::Args) -> Result<Self::Output, Self::Error> {
        // 调用 core/agent/{fs,kb,document,molecule}.rs 中的 native_* 自由函数
        Ok(fs_src::native_my_tool(&self.project_root, &args.arg))
    }
}

// 2. 在 core/agent/rig_adapter.rs::assemble_rig_tool_vec() 中注册
tools.push(Box::new(MyTool::new(project_root)));
```

### Adding a new API endpoint to Model Server

1. Add route function in `src/mbforge/server.py`
2. Register backend module in `src/mbforge/backends/` if new local model is needed
3. Add to `_BACKENDS` list for lifespan prewarm

### PDF 分子提取工作流

```bash
# CLI（Python，走 sidecar HTTP）
uv run python -m mbforge extract paper.pdf --output ./output/

# CLI（无 sidecar，直接加载模型）
uv run python -m mbforge extract paper.pdf --output ./out/ --no-sidecar

# Tauri invoke（前端调用）
invoke('extract_pdf_workflow_cmd', { path: '...', outputDir: '...' })
```

输出结构：`<output>/<pdf_name>/text.md` + `molecules/manifest.json` + 裁剪图片。提取完成后自动写入 SQLite。

### Adding a new PDF parser backend

1. Create client in `src-tauri/src/parsers/` (e.g., `myparser.rs`)
2. Implement `async fn parse(&self, input: &str) -> Result<ParsedOutput, String>`
3. Add variant in `pipeline.rs` parser selection logic

### 遇到报错时

停下来描述：(1) 错误现象 (2) 理解 (3) 解决方案，再行动。不要盲目穷举。

## Built-in Documentation

| 文档 | 位置 | 范畴 |
|------|------|------|
| Agent 工作规范 + 架构 | `AGENTS.md` | AI 编码助手操作手册 |
| 编码指南 | `CLAUDE.md` | Claude 上下文 + 架构速查 |
| 项目入口 | `README.md` | 人类用户/贡献者 |
| **文档治理规范** | `.claude/documentation-governance.md` | 描述文件分工与回刷机制 |
| 任务看板 | `TODO/INDEX.md` | 当前任务状态 |
| E-SMILES 规范 | `docs/esmiles-spec.md` | 分子表示规范 |
| MoleCode 规范 | `docs/molecode-spec.md` | 图语法规范 |
| 技术栈详情 | `docs/TECH_STACK.md` | 依赖选型详情 |
| 第三方引用 | `docs/REFERENCES.md` | 外部库与论文 |
| MoleCode 参考实现 | `ref/MoleCode/` | 参考代码 |
| 归档文档 | `docs/archive/` | 过时文档 |

