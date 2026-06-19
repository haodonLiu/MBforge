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
- **Rust** (`src-tauri/src/`): Agent ReAct 循环、PDF 原生解析（lopdf）、分子 SQLite 数据库、Tauri 命令层、化学信息学（chematic crate）、LLM 调用网关
- **Python** (`src/mbforge/`): FastAPI 模型服务器（port 18792）、Embedding、Rerank、MolDet（YOLO）、MolScribe

核心流程：PDF 解析 → 分子提取 → 向量知识库构建 → AI Agent 对话查询。
不允许任何基于假设或者推测的代码出现

总目的（详见 AGENTS.md §第一性原理）：**将非结构化的科学文献转化为可计算、可推理的分子知识，加速药物发现中的决策过程。**

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
│  │  Rust (src-tauri/src/)                          │    │
│  │  commands/ (IPC 命令层)                         │    │
│  │  core/ (Agent ReAct + 数据层 + 化学信息学)       │    │
│  │  parsers/ (PDF 解析管线)                        │    │
│  └──────────────────────┬──────────────────────────┘    │
│  ┌──────────────────────┴──────────────────────────┐    │
│  │  FastAPI Sidecar (port 18792, spawned by Tauri)  │    │
│  │  5 个后端: Embed / Rerank / MolDet / MolScribe   │    │
│  │  + 辅助端点: PDF render / health / environment   │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

**Dev mode**: Vite dev server proxies `/api/v1/*` to `localhost:18792` for sidecar health checks; all frontend business logic goes through `window.__TAURI__.invoke()`.
**Production**: Tauri shell spawns uvicorn as sidecar. Frontend communicates exclusively via Tauri IPC (Rust commands + events).

### Central Data Flow

PDF 经 Rust `parsers/pipeline.rs` 解析，流向两条路径：

```
PDF ─→ Rust parsers/pipeline.rs
  │
  ├─ 文档解析流程（抽取文本+图像+结构）
  │   ├─ classify:   parsers/structure/intent.rs → PDF type / structure
  │   ├─ extract:    parsers/pdf/{mineru,llama_parse,uniparser}.rs → Markdown
  │   ├─ images:     parsers/pdf/images.rs (lopdf) → embedded images
  │   ├─ ocr:        parsers/ocr/{paddle,uniparser}.rs → OCR 文本补充
  │   ├─ vlm:        parsers/chem/vlm_chem.rs → 化学结构图 VLM 识别
  │   ├─ associate:  parsers/chem/association.rs → 分子-文本关联
  │   ├─ validate:   parsers/chem/chem_validate.rs → 化学结构验证
  │   └─ report:     parsers/structure/{report,post_process,sections}.rs
  │
  ├─ 数据持久化（core/document/ + core/molecule/）
  │   ├─ core/document/knowledge_base.rs   → SQLite 知识库
  │   ├─ core/document/ingest_queue.rs      → 持久化处理队列
  │   ├─ core/document/file_cache.rs        → 文件解析缓存
  │   ├─ core/document/semantic_cache.rs    → 语义查询缓存
  │   ├─ core/molecule/molecule_store.rs    → 分子入库
  │   └─ core/molecule/molecule_db.rs       → 分子数据库 CRUD
  │
  └─ 查询路径
      ├─ core/vector/sqlite_vector_store.rs → 向量搜索 + FTS5
      └─ core/agent/ → ReAct 循环（LLM + 工具调用 + 记忆 + 轨迹审计）
```

### Sidecar Backends（Python, port 18792）

| 端点 | 后端模块 | 职责 |
|------|---------|------|
| `/api/v1/embed` | `backends/qwen3_embed.py` | 文本 → 384 维向量 |
| `/api/v1/rerank` | `backends/qwen3_rerank.py` | 搜索结果的语义重排序 |
| `/api/v1/moldet/*` | `backends/moldet.py` + `moldet_coref.py` | YOLO 分子检测 + 跨页关联 |
| `/api/v1/molscribe` | `backends/molscribe.py` | 分子结构图 → SMILES |
| `/api/v1/pdf/render-pages` | `server.py`（内联） | PDF 页面渲染（PyMuPDF） |

### 分子三层表示

MBForge 使用三层分子表示，逐层可逆。详见 AGENTS.md §分子三层表示：

| 层级 | 格式 | 存储 | 用途 |
|------|------|------|------|
| Layer 1 | SMILES | `molecules.db` `smiles` 列 (NOT NULL) | RDKit 兼容、指纹计算、子结构搜索 |
| Layer 2 | E-SMILES | `molecules.db` `esmiles` 列 (nullable) | 语义标签（`<a>N:GROUP</a>`），Markush 结构 |
| Layer 3 | MoleCode | 运行时生成（不持久化） | LLM 推理用，Mermaid 图语法，显式拓扑 |

转换通路（纯 Rust，`core/chem/{esmiles,molecode,abbreviation_map}.rs`）：
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

### Adding a new Tauri command

1. Add the command function in the appropriate `commands/{module}.rs` file (or create a new one)
2. Add `pub mod {module};` in `commands/mod.rs`
3. Add the function to `generate_handler![]` macro in `commands/mod.rs::handler()`
4. Register the frontend API wrapper in `frontend/src/api/tauri/{module}.ts`

### Adding a new API endpoint to Model Server

1. Add route function in `src/mbforge/server.py`
2. Register backend module in `src/mbforge/backends/` if new local model is needed
3. Add to `_BACKENDS` list for lifespan prewarm

### Adding a new PDF parser backend

1. Create client in `src-tauri/src/parsers/pdf/` (e.g., `myparser.rs`)
2. Implement `async fn parse(&self, input: &str) -> Result<ParsedOutput, String>`
3. Add variant in `parsers/pipeline.rs::extract` parser selection logic
4. Register module in `parsers/pdf/mod.rs`

### 遇到报错时

停下来描述：(1) 错误现象 (2) 理解 (3) 解决方案，再行动。不要盲目穷举。

## Built-in Documentation

| 文档 | 位置 | 范畴 |
|------|------|------|
| **总目的与缺失分析** | `AGENTS.md` | 第一性原理：我们在建什么、还缺什么 |
| Agent 工作规范 + 架构 + 编码规范 | `AGENTS.md` | AI 编码助手完整操作手册 |
| 本文件 | `CLAUDE.md` | Claude 上下文 + 架构速查 |
| 项目入口 | `README.md` | 人类用户/贡献者 |
| **文档治理规范** | `.claude/documentation-governance.md` | 描述文件分工与回刷机制 |
| 任务看板 | `TODO/INDEX.md` | 当前任务状态 |
| E-SMILES 规范 | `docs/specs/esmiles-spec.md` | 分子表示规范 |
| MoleCode 规范 | `docs/specs/molecode-spec.md` | 图语法规范 |
| 技术栈详情 | `docs/TECH_STACK.md` | 依赖选型详情 |
| 第三方引用 | `docs/REFERENCES.md` | 外部库与论文 |
| MoleCode 参考实现 | `ref/MoleCode/` | 参考代码 |

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (60-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk go test             # Go test failures only (90%)
rtk jest                # Jest failures only (99.5%)
rtk vitest              # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk pytest              # Python test failures only (90%)
rtk rake test           # Ruby test failures only (90%)
rtk rspec               # RSpec test failures only (60%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%). Format flags (-c, -l, -L, -o, -Z) run raw.
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->