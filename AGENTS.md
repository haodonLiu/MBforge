# MBForge Agent 工作规范

> 本文档面向 AI 编码助手。阅读本文档前，默认你对本项目一无所知。
> MBForge 是一个面向分子科学/药物发现的桌面端知识库平台，采用 React + Vite + Tauri + Rust + Python 双语言架构。

---

## 项目概览

**MBForge**（Molecular Knowledge Base & AI Workbench）的核心流程是：

```
PDF 解析 → 分子提取 → 向量知识库构建 → AI Agent 对话查询
```

- **前端**：React 19 + Vite 6 + TypeScript 5.7，运行于浏览器/Tauri WebView
- **桌面壳**：Tauri v2（Rust），负责系统调用、SQLite 持久化、PDF 原生解析、Agent ReAct 循环
- **Python 侧载（Sidecar）**：FastAPI 模型服务器（port 18792），负责 LLM/Embedding/VLM 推理、ChromaDB 向量库、MolScribe 分子图像识别

**双语言分工**：
- **Rust**（`src-tauri/src/`，~9,700 行）：Agent 循环、PDF 原生解析（lopdf）、分子 SQLite 数据库、Tauri IPC 命令层
- **Python**（`src/mbforge/`，~12,900 行）：FastAPI REST API、LLM/Embedding/VLM 模型推理、ChromaDB、MolScribe

---

## 技术栈

| 层级 | 技术 | 版本/说明 |
|------|------|-----------|
| 前端 | React, Vite, TypeScript | 19, 6, ~5.7 |
| 桌面壳 | Tauri v2 | Rust 2021 edition |
| Rust 核心 | lopdf, rusqlite, reqwest, tokio, serde, regex | 见 `src-tauri/Cargo.toml` |
| Python 服务 | FastAPI, uvicorn | >=0.115, >=0.34 |
| 向量数据库 | ChromaDB | >=0.4 |
| 化学信息学 | RDKit, OpenBabel | >=2024.3 |
| 深度学习 | PyTorch (CUDA 12.8) | >=2.6 |
| Embedding | sentence-transformers | >=2.5 |
| PDF 解析 | PyMuPDF, pdfplumber, lopdf (Rust) | — |
| 分子检测 | ultralytics (YOLO) | >=8.3 |
| 包管理 | uv (Python), Cargo (Rust), npm (前端) | — |

---

## 项目结构

```
MBForge/
├── frontend/               # React + Vite 前端
│   ├── src/
│   │   ├── api/            # HTTP 客户端 + Tauri invoke 桥接
│   │   ├── components/     # UI 组件（Chat, MoleculeLibrary, PDFViewer, ...）
│   │   ├── hooks/          # React Hooks
│   │   ├── types/          # TypeScript 类型定义
│   │   └── App.tsx         # 路由入口
│   ├── package.json
│   ├── tsconfig.json       # TypeScript 严格模式
│   └── vite.config.ts      # Vite 配置，开发时代理 /api → localhost:18792
│
├── src-tauri/              # Rust Tauri 后端
│   ├── src/
│   │   ├── main.rs         # Tauri 入口：命令注册 + Python sidecar 管理
│   │   ├── lib.rs          # 模块导出
│   │   ├── commands/       # Tauri IPC 命令层（6 模块，25+ 命令）
│   │   ├── core/           # Agent + 数据层（26 模块）
│   │   │   ├── agent.rs    # ReAct Agent 核心循环
│   │   │   ├── executor.rs # 20+ 工具执行器
│   │   │   ├── llm.rs      # LLM HTTP 客户端
│   │   │   ├── molecule_store.rs   # SQLite + FTS5 分子数据库
│   │   │   ├── memory.rs           # 6 分类持久记忆
│   │   │   └── vector_store.rs     # 向量存储/检索
│   │   └── parsers/        # PDF 解析管线（16 模块）
│   │       ├── pipeline.rs # 统一解析管线（Stage 1-6）
│   │       ├── association.rs      # 分子-文本关联引擎
│   │       ├── images.rs           # lopdf 图像提取
│   │       ├── mineru.rs           # MinerU API 客户端
│   │       ├── llama_parse.rs      # LlamaParse API 客户端
│   │       └── uniparser.rs        # UniParser API 客户端
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   └── .cargo/config.toml  # dev 环境屏蔽 warnings
│
├── src/mbforge/            # Python 模型服务器 & 核心库
│   ├── model_server/       # FastAPI 服务
│   │   ├── main.py         # 入口 + 路由注册
│   │   ├── agent_manager.py# Agent 桥接单例管理
│   │   ├── dependencies.py # 依赖注入
│   │   ├── models/         # LLM/Embed/Rerank/VLM/MolDet 单例管理
│   │   └── routers/        # 15 个 API 路由模块
│   ├── core/               # Python 数据层
│   │   ├── project.py      # Vault 项目管理
│   │   ├── knowledge_base.py       # ChromaDB 向量知识库
│   │   ├── mol_database.py         # SQLite 分子数据库
│   │   └── summarizer.py           # L0/L1/L2 分层摘要
│   ├── models/             # AI 模型抽象层
│   │   ├── base.py, llm.py, anthropic_llm.py, embedding.py, vlm.py
│   ├── parsers/            # Python 解析层
│   │   ├── pdf_parser.py           # PDFParserPipeline（PyMuPDF）
│   │   └── molecule/               # 分子提取管线 + MolScribe
│   ├── agent/              # Python 工具框架
│   ├── csar/               # SAR 分析工具箱
│   ├── molecules/          # 分子数据合约
│   └── cli.py              # CLI 入口（mbforge / csar 命令）
│
├── tests/                  # Python 测试
│   ├── unit/               # 单元测试（知识库、分子数据库、Agent 优化等）
│   ├── parser_io/          # 解析器 I/O 测试
│   └── integration/output/ # 集成测试输出/参考数据
│
├── setup/                  # 一键安装脚本
│   ├── index.sh / index.bat
│   ├── modules/            # 8 步配置脚本
│   └── MolScribe/          # MolScribe 完整代码
│
├── docs/                   # 项目文档
│   ├── TECH_STACK.md
│   ├── REFERENCES.md
│   ├── pdf-extraction-workflow.md
│   ├── pipeline-migration-plan.md
│   ├── pipeline-redesign.md
│   └── pdf-pipeline-test/  # 管线测试用例与参考输出
│
├── pyproject.toml          # Python 项目配置（uv + setuptools）
├── uv.lock                 # Python 依赖锁定
├── package.json            # 根级 npm 配置（空对象，前端配置在 frontend/）
└── .env.template           # 环境变量模板（API 密钥、模型配置等）
```

---

## 构建与运行命令

### 依赖安装

```bash
# Python 依赖（使用 uv）
uv sync --dev

# 前端依赖
npm install
```

### 开发模式（需同时启动两个服务）

```bash
# 终端 1：启动 Python 模型服务器
uv run uvicorn mbforge.model_server.main:app --host 127.0.0.1 --port 18792

# 终端 2：启动前端开发服务器（Vite port 5173，自动代理 /api 到 18792）
cd frontend && npm run dev

# 终端 3：启动 Tauri 桌面壳（如需要 Rust 侧开发）
cd src-tauri && cargo tauri dev
```

### 编译检查

```bash
# Rust
nvidia-smi ; if (-not $?) { Write-Host "No CUDA" }
# Rust 编译检查
cd src-tauri && cargo check

# Rust 编译时 warnings 被 `.cargo/config.toml` 屏蔽，仅显示 errors
# 如需恢复 warnings，临时注释掉 `src-tauri/.cargo/config.toml` 中的 rustflags 行

# 前端类型检查
cd frontend && npx tsc --noEmit
```

### 生产构建

```bash
# 前端构建（输出到 frontend/dist）
cd frontend && npm run build

# 打包桌面应用（Tauri 会自动先构建前端）
cd src-tauri && cargo tauri build
```

---

## 测试命令

### Rust 测试

Rust 侧测试数量较多（~145 个），**开发时优先运行目标模块测试**，全量测试仅用于 CI/发布前。

```bash
# 核心数据层
cargo test --lib embedding::
cargo test --lib vector_store::
cargo test --lib knowledge_base::
cargo test --lib document_tree::

# 解析层
cargo test --lib headings::
cargo test --lib sections::
cargo test --lib pipeline::

# Agent 层
cargo test --lib executor::

# 全量测试（仅 CI / 发布前）
cd src-tauri && cargo test --lib
```

也可使用 PowerShell 快捷脚本：
```powershell
cd src-tauri
.\test-quick.ps1
```

### Python 测试

```bash
# 运行全部 Python 测试
uv run pytest tests/ -v

# 代码检查与格式化
uv run ruff check src/
uv run ruff format src/ --check
```

---

## 代码风格规范

- **Rust**：遵循现有代码风格，**不引入新 lint 规则**。dev 环境已配置 `rustflags = ["-A", "warnings"]`，cargo 默认只看 errors。
- **Python**：保留现有代码，**迁移期不强制修改旧代码**。使用 ruff 进行 lint 和 format。
- **前端**：TypeScript **严格模式**已启用（`tsconfig.json` 中 `strict: true`, `noUnusedLocals: true`, `noUnusedParameters: true`）。
- **模块导入**：前端使用 `@/` 别名指向 `src/`；Python 测试通过 `conftest.py` 将 `src/` 加入 `sys.path`。

---

## 模块边界与架构约定

### 三层架构

| 层级 | 目录 | 职责 | 关键文件 |
|------|------|------|----------|
| **UI 层** | `frontend/src/` | React 组件、页面路由、状态管理 | `App.tsx`, `api/tauri-bridge.ts` |
| **命令层** | `src-tauri/src/commands/` | Tauri IPC 命令注册，桥接前端与 Rust 核心 | `main.rs` 中的 `invoke_handler` |
| **核心层** | `src-tauri/src/core/` | Rust Agent、数据持久化、向量存储、分子数据库 | `agent.rs`, `executor.rs`, `molecule_store.rs` |
| **解析层** | `src-tauri/src/parsers/` | PDF 解析管线、图像提取、关联引擎 | `pipeline.rs`, `association.rs`, `images.rs` |
| **模型服务** | `src/mbforge/model_server/` | FastAPI REST API、模型单例管理 | `main.py`, `routers/*.py` |

### 新增代码的约定

1. **新增 Rust Tauri 命令**：
   - 在 `src-tauri/src/commands/` 的适当模块中定义 `#[tauri::command]` 函数
   - 在 `src-tauri/src/main.rs` 的 `invoke_handler!` 宏中注册

2. **新增 Rust Agent 工具**：
   - 在 `src-tauri/src/core/tools.rs` 注册 `ToolInfo`（名称、描述、参数 Schema）
   - 在 `src-tauri/src/core/executor.rs` 添加匹配分支的执行逻辑

3. **新增 FastAPI 路由**：
   - 在 `src/mbforge/model_server/routers/` 创建 `APIRouter`
   - 在 `src/mbforge/model_server/main.py` 通过 `app.include_router()` 注册

4. **新增 PDF 解析后端**：
   - 在 `src-tauri/src/parsers/` 创建客户端模块（如 `myparser.rs`）
   - 在 `src-tauri/src/parsers/pipeline.rs` 的解析器选择逻辑中添加分支

---

## 迁移期规则（重要）

本项目处于 **Python → Rust 迁移期**，必须遵守：

- **Rust 新代码优先，Python 代码冻结**（除 bugfix 外不修改）
- **新增功能必须在 Rust 侧实现**
- **Python sidecar 仅保留**：模型推理（Embedding/VLM/LLM）、MolDetv2 分子检测、MolScribe 图像识别
- **前端调用逐步从 HTTP API 迁移到 Tauri `invoke()`**

---

## 配置系统

项目采用**两级配置**：

1. **全局配置**：`~/.config/MBForge/config.json`（`AppConfig`）
   - LLM provider、embedding 模型、rerank 模型、VLM 设置等
2. **项目级配置**：项目目录下的 `.mbforge/settings.json`（`ProjectSettings`）
   - 模型覆盖、workflow 开关、项目特定选项

**环境变量**（`.env` 文件，不要提交到版本库）：
- `MBFORGE_LLM_*`：LLM 配置（provider、base_url、api_key、model）
- `MBFORGE_EMBED_*`：Embedding 配置
- `MBFORGE_RERANK_*`：Rerank 配置
- `UNIPARSER_HOST` / `UNIPARSER_API_KEY`：UniParser 远程解析
- `MINERU_HOST` / `MINERU_API_KEY`：MinerU 文档解析
- `HF_HOME` / `MODELSCOPE_CACHE` / `TORCH_HOME`：模型缓存目录

配置优先级：**GUI 设置 > 环境变量 > 默认值**

---

## 安全注意事项

- **`.env` 文件包含 API 密钥**，已列入 `.gitignore`，**严禁提交**
- Tauri 生产构建的 CSP 已禁用（`dangerousDisableAssetCspModification: true`），前端资源加载无额外限制
- 生产环境中 Tauri 会自动启动 Python sidecar（uvicorn），窗口关闭时自动终止子进程
- 开发模式下可设置 `MBFORGE_NO_SPAWN=1` 禁止 Tauri 自动启动 Python sidecar

---

## 性能优化要点

- **Rust 共享 HTTP 客户端**：`core/http.rs` 提供 4 个按超时分类的 `LazyLock` 单例，避免每次请求新建连接池
- **Python 异步非阻塞**：所有模型推理路由通过 `run_in_executor` 包装，不阻塞事件循环
- **启动模型预热**：FastAPI lifespan 在后台线程预加载 LLM/Embedder/Reranker，首次请求零延迟
- **requests.Session 复用**：UniParser 客户端使用持久连接，减少 TCP 握手开销

---

## 关键文档索引

| 文档 | 位置 | 内容 |
|------|------|------|
| 技术栈详情 | `docs/TECH_STACK.md` | 所有依赖的技术选型、版本、使用场景 |
| 第三方引用 | `docs/REFERENCES.md` | 外部库、论文、数据引用 |
| PDF 迁移规划 | `docs/pipeline-migration-plan.md` | Python→Rust 迁移路线图 |
| 管线重设计 | `docs/pipeline-redesign.md` | 解析管线增量重设计 |
| PDF 提取工作流 | `docs/pdf-extraction-workflow.md` | 端到端 PDF 处理流程 |
| E-SMILES 规范 | `src-tauri/docs/esmiles/` | E-SMILES 格式 + MBForge 集成 |
| LiteParse API | `src-tauri/docs/liteparse/` | LiteParse API 参考存档 |
| AI 编码指南 | `CLAUDE.md` | Claude Code 专用指南（含代码示例） |
