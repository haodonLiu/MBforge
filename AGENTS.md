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
- **Rust**（`src-tauri/src/`）：Agent 循环、PDF 原生解析（lopdf）、分子 SQLite 数据库、Tauri IPC 命令层
- **Python**（`src/mbforge/`）：FastAPI REST API、LLM/Embedding/VLM 模型推理、ChromaDB、MolScribe

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
│   │   ├── api/            # Tauri invoke 桥接 + HTTP fallback
│   │   ├── components/     # 38 个 UI 组件（Chat, MoleculeLibrary, Search, ...）
│   │   │   ├── ui/         # 21 个原子组件（Button, Modal, Card, ...）
│   │   │   ├── settings/   # 设置/模型管理组件
│   │   │   ├── animations/ # 动画包装组件
│   │   │   └── project/    # 项目仪表盘组件
│   │   ├── hooks/          # React Hooks（useTheme, useToast, ...）
│   │   ├── context/        # React Context 入口
│   │   ├── types/          # TypeScript 类型定义
│   │   ├── utils/          # 工具函数（ROI 文本提取）
│   │   ├── styles/         # 全局 CSS 变量/主题
│   │   ├── App.tsx         # 路由入口
│   │   └── main.tsx        # 应用入口
│   ├── package.json
│   ├── tsconfig.json       # TypeScript 严格模式
│   └── vite.config.ts      # Vite 配置，开发时代理 /api → localhost:18792
│
├── src-tauri/              # Rust Tauri 后端
│   ├── src/
│   │   ├── main.rs         # Tauri 入口：30+ 命令注册 + Python sidecar 管理
│   │   ├── lib.rs          # 模块导出
│   │   ├── commands/       # Tauri IPC 命令层（11 模块，30+ 命令）
│   │   ├── core/           # Agent + 数据层（32 模块）
│   │   │   ├── agent.rs    # ReAct Agent 核心循环
│   │   │   ├── executor.rs # 25+ 工具执行器
│   │   │   ├── llm.rs      # LLM HTTP 客户端
│   │   │   ├── molecule_store.rs   # SQLite + FTS5 分子数据库
│   │   │   ├── memory.rs           # 6 分类持久记忆
│   │   │   ├── markush.rs          # E-SMILES Markush 分析
│   │   │   ├── resource_manager.rs # 统一资源管理
│   │   │   └── semantic_cache.rs   # 三级语义缓存
│   │   └── parsers/        # PDF 解析管线（19 模块）
│   │       ├── pipeline.rs # 统一解析管线（Stage 0-7）
│   │       ├── association.rs      # 分子-文本关联引擎
│   │       ├── images.rs           # lopdf 图像提取
│   │       ├── claim_parser.rs     # 专利 Claims 解析
│   │       ├── claim_policy.rs     # 专利范围匹配
│   │       ├── molecule_extractor.rs # 专利命名化合物提取
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
│   │   ├── dependencies.py # 依赖注入
│   │   ├── models/         # LLM/Embed/Rerank/VLM/MolDet 单例管理
│   │   └── routers/        # 16 个 API 路由模块
│   ├── core/               # Python 数据层
│   │   ├── project.py      # Vault 项目管理
│   │   ├── knowledge_base.py       # ChromaDB 向量知识库
│   │   ├── mol_database.py         # SQLite 分子数据库
│   │   ├── resource_manager.py     # 资源管理 + ModelScope 下载
│   │   └── summarizer.py           # L0/L1/L2 分层摘要
│   ├── models/             # AI 模型抽象层
│   │   ├── base.py, llm.py, anthropic_llm.py, embedding.py, vlm.py, rerank.py, rerank_qwen3.py
│   ├── parsers/            # Python 解析层（PDF 解析全在 Rust 侧）
│   │   └── molecule/       # MolDet + MolScribe 图像分子提取管线
│   │       ├── molscribe/           # MolScribe 门面类
│   │       └── molscribe_inference/ # MolScribe 推理引擎
│   ├── csar/               # SAR 分析工具箱（占位模块，仅 __init__.py）
│   ├── molecules/          # 分子数据合约
│   ├── utils/              # 配置、常量、异常、GPU 检测、日志
│   └── cli.py              # CLI 入口（mbforge 命令）
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
│   └── migration-agent-*.md # 迁移代理日志
│
├── CODEMAP.md              # 代码逻辑树（最详细模块清单）
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

### 通用原则

1. **显式优于隐式**：类型注解、错误处理、返回值必须明确，禁止依赖隐式转换或全局魔术状态。
2. **DRY**：重复超过 2 次的逻辑必须抽取为函数/宏/工具类。
3. **KISS**：优先使用标准库和已引入依赖的内置能力，避免过度封装。
4. **最小变更**：修复 bug 或添加功能时，改动范围尽可能小，不重构无关代码。
5. **常量同步**：Rust (`src-tauri/src/core/constants.rs`) 与 Python (`src/mbforge/utils/constants.py`) 的同名常量必须保持值一致，修改时双侧同步更新。

### Rust（`src-tauri/src/`）

| 项 | 规范 |
|---|---|
| 缩进 | 4 空格 |
| 引号 | 单引号 `'` 用于字符，字符串两种皆可，但现有代码以双引号 `"` 为主，保持统一 |
| 命名 | 函数/变量 `snake_case`；类型/结构体/枚举 `PascalCase`；常量 `SCREAMING_SNAKE_CASE`；模块 `snake_case` |
| 注释 | 公共 API 用 `///` 文档注释；内部逻辑用 `//`；模块级说明用 `//!` |
| 错误处理 | 函数签名返回 `Result<T, String>`（或自定义 `Error`），调用链用 `?`；禁止 `unwrap()` / `expect()`，除非在单元测试或初始化代码中 |
| 日志 | `log::info!` / `log::warn!` / `log::error!` / `log::debug!`，禁止 `println!` |
| 导入排序 | 1) `std::` / `core::` 2) 第三方 crate 3) `crate::` / `super::` |
| 并发状态 | Tauri 状态使用 `Arc<RwLock<T>>` 模式，读多写少时用 `RwLock`，写操作用 `.write().await` |
| Unsafe | **禁止**引入新的 `unsafe` 代码块 |
| 路径安全 | **必须**使用 `core/helpers.rs` 中的 `assert_within_root()` 或 `safe_join()` 进行路径安全检查；禁止直接使用 `Path::join()` 后直接访问文件系统 |
| Dev 编译 | `.cargo/config.toml` 已屏蔽 warnings，CI 构建前需确认 `cargo check` 零 errors |

### Python（`src/mbforge/`）

| 项 | 规范 |
|---|---|
| 缩进 | 4 空格 |
| 引号 | 双引号 `"` 为主；docstring 使用三双引号 `"""` |
| 命名 | 函数/变量 `snake_case`；类 `PascalCase`；常量 `SCREAMING_SNAKE_CASE`；模块 `snake_case` |
| 注释 | 模块/函数使用 Google-style docstring（简要描述 + Args/Returns）；行内注释用 `# ` |
| 类型注解 | 所有公共函数必须有参数类型和返回类型注解；使用 `from __future__ import annotations` 避免运行时引用问题 |
| 错误处理 | 业务异常继承 `MBForgeError`；FastAPI 路由通过 `@app.exception_handler(MBForgeError)` 统一捕获并返回结构化 JSON；禁止裸 `except:` |
| 日志 | 统一使用 `from ...utils.logger import get_logger; logger = get_logger(__name__)`，禁止 `print()` |
| 异步 | I/O 阻塞操作（模型推理、文件读写）必须用 `await loop.run_in_executor(None, ...)` 包装，不得阻塞事件循环 |
| 导入排序 | 1) `from __future__` 2) 标准库 3) 第三方库 4) 本地绝对导入 `from mbforge.xxx` 5) 相对导入 `from ...xxx` |
| 格式化 | 使用 `ruff format src/`（行宽默认 88）；`ruff check src/` 检查 lint |
| 冻结期 | **迁移期不强制修改旧代码**，新增/修改的代码必须遵守本规范 |

### TypeScript / 前端（`frontend/src/`）

| 项 | 规范 |
|---|---|
| 缩进 | 2 空格 |
| 引号 | 单引号 `'` |
| 分号 | **省略**（无分号风格） |
| 命名 | 组件/类型/接口 `PascalCase`；函数/变量/属性 `camelCase`；常量 `SCREAMING_SNAKE_CASE` 或 `camelCase`；文件 `PascalCase.tsx`（组件）或 `camelCase.ts`（工具） |
| 类型 | 优先使用 `interface` 定义数据结构；使用 `import type` 导入仅作类型使用的符号；**严格模式**强制开启（`strict: true`, `noUnusedLocals: true`, `noUnusedParameters: true`, `noFallthroughCasesInSwitch: true`） |
| 组件 | 使用 `export default function ComponentName()` 定义页面级组件；局部 UI 用 `function SubComponent()`； Hooks 用 `useXxx` 前缀 |
| JSX 样式 | 优先使用 CSS 变量（`var(--xxx)`）和全局样式类；内联 `style` 仅用于动态计算值；禁止在 JSX 中写大型 CSS 对象，超过 3 个属性的内联样式应提取为类或 styled 组件 |
| 动画 | **必须**使用 `hooks/useAnimations.ts` 中的预定义动画变体；禁止在组件中重复定义 `motion.div` 的 `initial/animate/exit/transition` 参数；交互式动画（如焦点状态）可直接使用 `animate={{ ... }}` |
| 错误处理 | API 调用使用 `try/catch`；异步函数返回 `{ success: boolean; error?: string }` 时，调用方必须检查 `success` |
| 路径 | 统一使用 `@/` 别名指向 `src/`，禁止相对路径 `../../` 超过两级 |
| React Hooks | 遵守 Rules of Hooks（顶层调用，不在循环/条件中）；`useEffect` 依赖数组必须完整；`useCallback` / `useMemo` 仅在计算昂贵或引用稳定性必要时使用 |
| 状态管理 | 局部状态用 `useState`；跨组件状态优先通过 props 传递，复杂场景使用 React Context（`frontend/src/context/`） |

### Import 排序（通用）

所有语言遵循**三组分离**原则，组内按字母顺序排序：

1. **标准库**（`std::`, `import os`, `import React`）
2. **第三方依赖**（`tokio::`, `from fastapi import`, `from framer-motion`）
3. **项目内部**（`crate::`, `from mbforge::`, `from '@/components'`）

空行分隔三组。

---

## 模块边界与架构约定

### 三层架构

| 层级 | 目录 | 职责 | 关键文件 |
|------|------|------|----------|
| **UI 层** | `frontend/src/` | React 组件、页面路由、状态管理 | `App.tsx`, `api/tauri-bridge.ts` |
| **命令层** | `src-tauri/src/commands/` | Tauri IPC 命令注册，桥接前端与 Rust 核心 | `main.rs` 中的 `invoke_handler` |
| **核心层** | `src-tauri/src/core/` | Rust Agent、数据持久化、向量存储、分子数据库、项目迁移 | `agent.rs`, `executor.rs`, `molecule_store.rs`, `project_migrator.rs` |
| **解析层** | `src-tauri/src/parsers/` | PDF 解析管线、图像提取、关联引擎 | `pipeline.rs`, `association.rs`, `images.rs` |
| **模型服务** | `src/mbforge/model_server/` | FastAPI REST API、模型单例管理 | `main.py`, `routers/*.py` |

### 目录与文件组织

| 规则 | 示例 |
|------|------|
| 一个文件一个主要职责 | `frontend/src/components/Chat.tsx` 只负责对话 UI |
| 组件超过 300 行必须拆分 | 将子组件提取到同一目录的独立文件 |
| UI 组件按功能分组 | `frontend/src/components/ui/` 放置通用原子组件（Button、Input、Avatar） |
| Rust 模块按职责分组 | `commands/`（IPC）、`core/`（业务）、`parsers/`（解析），禁止跨层直接调用 |
| Python 路由模块化 | 每个路由模块只处理一类资源（`llm.py`、`molecule.py`、`project.py`） |
| 常量集中管理 | Rust 用 `core/constants.rs`；Python 用 `utils/constants.py`；禁止魔法字符串散落 |

### 新增代码的约定

1. **新增 Rust Tauri 命令**：
   - 在 `src-tauri/src/commands/` 的适当模块中定义 `#[tauri::command]` 函数
   - 命令函数命名：`{模块}_{动作}`，如 `agent_init`、`mol_store_search`
   - 在 `src-tauri/src/main.rs` 的 `invoke_handler!` 宏中注册
   - 如需新状态类型，在命令模块中定义 `*State` 结构体，在 `main.rs` 中 `.manage()`

2. **新增 Rust Agent 工具**：
   - 在 `src-tauri/src/core/executor.rs` 的 `ToolExecutor` 中注册 `ToolInfo`（名称、描述、参数 JSON Schema）
   - 在同一文件的执行匹配分支中实现工具逻辑
   - 工具名使用 `snake_case`，描述必须清晰说明输入输出格式

3. **新增 FastAPI 路由**：
   - 在 `src/mbforge/model_server/routers/` 创建 `APIRouter`
   - 路由前缀统一使用 `/api/v1/{资源名}`
   - 在 `src/mbforge/model_server/main.py` 通过 `app.include_router()` 注册
   - 路由函数必须有类型注解和 docstring

4. **新增 PDF 解析后端**：
   - 在 `src-tauri/src/parsers/` 创建客户端模块（如 `myparser.rs`）
   - 实现异步解析接口：`async fn parse(&self, input: &str) -> Result<ParsedOutput, String>`
   - 在 `src-tauri/src/parsers/pipeline.rs` 的解析器选择逻辑中添加分支

5. **新增前端页面/组件**：
   - 页面级组件放入 `frontend/src/components/`，命名 `PascalCase.tsx`
   - 组件 props 使用 `interface` 定义，不允许使用 `any`
   - 组件内部状态复杂时拆分为自定义 Hook，放入 `frontend/src/hooks/`
   - 新增 API 调用统一放入 `frontend/src/api/`，优先使用 Tauri `invoke()`，HTTP fallback 标记为 `// DEV ONLY`

---

## 迁移期规则（重要）

本项目处于 **Python → Rust 迁移期**，必须遵守：

- **Rust 新代码优先，Python 代码冻结**（除 bugfix 外不修改）
- **新增功能必须在 Rust 侧实现**
- **Python sidecar 仅保留**：模型推理（Embedding/VLM/LLM）、MolDetv2 分子检测、MolScribe 图像识别
- **前端调用逐步从 HTTP API 迁移到 Tauri `invoke()`**

---

## 命名约定

### 跨语言命名一致性

| 概念 | Rust | Python | TypeScript |
|------|------|--------|------------|
| 文件/模块 | `snake_case.rs` | `snake_case.py` | `PascalCase.tsx`（组件）/`camelCase.ts`（工具） |
| 类型/类 | `PascalCase` | `PascalCase` | `PascalCase`（interface/type/class） |
| 函数/方法 | `snake_case` | `snake_case` | `camelCase` |
| 变量/属性 | `snake_case` | `snake_case` | `camelCase` |
| 常量 | `SCREAMING_SNAKE_CASE` | `SCREAMING_SNAKE_CASE` | `SCREAMING_SNAKE_CASE` |
| 枚举成员 | `PascalCase` | `PascalCase`（或 `UPPER_CASE`） | `PascalCase` |
| 泛型参数 | `T`, `K`, `V` | — | `T`, `K`, `V` |
| 生命周期 | `'a`, `'src` | — | — |

### 特殊命名规则

- **布尔变量**：使用 `is_` / `has_` / `can_` 前缀，如 `is_loading`、`has_documents`
- **集合变量**：使用复数名词，如 `documents`（而非 `doc_list`）、`entries`
- **回调函数**：使用 `on_` / `handle_` 前缀，如 `on_click`、`handle_submit`
- **Hook**：React Hooks 必须以 `use` 开头，如 `use_project_root`
- **命令函数**：Tauri 命令使用 `{模块}_{动作}`，如 `agent_init`、`mol_store_search`
- **路由函数**：FastAPI 路由使用动作名词，如 `chat_stream`、`list_molecules`
- **状态类型**：`*State`，如 `AgentState`、`MolDbState`
- **错误类型**：`*Error`，如 `ModelNotAvailableError`
- **结果类型**：`*Result`，如 `PdfParseResult`

---

## 注释与文档规范

### 必须写文档注释的场景

- 所有 `pub` 的 Rust 函数/结构体/模块
- 所有公共 Python 函数/类/模块
- 所有导出的 TypeScript 类型/函数/组件
- 复杂的算法、非显而易见的业务逻辑
- 跨语言边界的数据结构（如 Tauri IPC 传参类型）

### 注释格式

**Rust**：
```rust
/// 简要描述（一行）。
/// 详细说明（如需）。
/// # Arguments
/// - `arg`：参数说明
/// # Returns
/// 返回值说明
/// # Errors
/// 可能的错误情况
pub fn my_fn(arg: &str) -> Result<String, String> {
```

**Python**：
```python
def my_fn(arg: str) -> str:
    """简要描述。

    Args:
        arg: 参数说明。

    Returns:
        返回值说明。

    Raises:
        MBForgeError: 错误情况。
    """
```

**TypeScript**：
```typescript
/**
 * 简要描述。
 * @param arg - 参数说明
 * @returns 返回值说明
 */
export function myFn(arg: string): string {
```

### 行内注释

- 使用 `// `（Rust/TS）或 `# `（Python），后面必须跟一个空格
- 解释"为什么"而非"做什么"（代码本身应该说明做什么）
- 禁止用注释禁用代码（要删就删，git 会保留历史）

### TODO / FIXME / NOTE / HACK

- `TODO`：已知待实现的功能，必须附带 issue 或作者标识，如 `// TODO(kimi): 添加分页支持`
- `FIXME`：已知有问题的代码，需要后续修复
- `NOTE`：对后续维护者的关键提醒
- `HACK`：临时绕过方案，必须说明原因和预期移除条件
- **禁止**在生产代码中遗留无标识的 `TODO`

---

## 错误处理模式

### Rust

- **函数签名**：返回 `Result<T, String>` 或自定义 `Error` 类型
- **调用链**：使用 `?` 传播错误；禁止 `unwrap()` / `expect()`（测试除外）
- **错误信息**：必须包含上下文，如 `"Project migration failed: {e}"` 而非 `"Error occurred"`
- **用户-facing 错误**：Tauri 命令返回 `Result<T, String>`，String 为可读错误信息
- **日志**：错误发生时必须记录 `log::error!`，包含足够上下文

### Python

- **业务异常**：继承 `MBForgeError`，包含 `status_code`、`message`、`error_code`
- **FastAPI 统一处理**：`@app.exception_handler(MBForgeError)` 自动转为 `{success: false, error: ..., error_code: ...}`
- **模型推理错误**：捕获后设置模型状态为 `error`，记录详细 traceback，返回友好消息
- **禁止**裸 `except:`，必须捕获具体异常类型

### TypeScript

- **API 调用**：使用 `try/catch`，错误信息展示给用户
- **类型守卫**：处理后端返回的 `error?: string` 字段，禁止假设接口总是成功
- **Tauri invoke**：捕获 `Error`，将 `e.message` 展示在 UI 中
- **组件错误边界**：关键页面使用 Error Boundary 防止整页白屏

---

## 前端开发规范

### 组件设计

1. **单一职责**：一个组件只做一件事，超过 300 行拆分
2. **Props 优先**：优先通过 props 传递数据，避免过度使用 Context
3. **受控组件**：表单元素优先使用受控模式（`value` + `onChange`）
4. **无障碍**：图片必须有 `alt`，交互元素必须有 `aria-label`，颜色对比度满足 WCAG AA

### 样式规范

1. **CSS 变量**：主题色、间距、圆角必须使用 CSS 变量（`var(--accent)`、`var(--bg-surface)`）
2. **深色模式**：所有新增样式必须测试深色模式兼容性；避免硬编码白色/黑色
3. **内联样式限制**：JSX 中 `style` 对象不超过 3 个属性，超出则提取为 CSS 类
4. **响应式**：使用 flex/grid 布局，避免固定像素宽度；断点通过 CSS 变量或媒体查询管理

### 状态管理

1. **局部状态**：`useState` 处理组件内部状态
2. **共享状态**：通过 props 向下传递；跨多层时考虑 Context
3. **持久状态**：用户设置、LLM 配置使用 `localStorage`，键名以 `mbforge_` 前缀
4. **异步状态**：数据获取使用 `useEffect` + `useState`，复杂场景使用自定义 Hook

### 性能

1. **Memoization**：仅在计算昂贵或引用稳定性必要时使用 `useMemo` / `useCallback`
2. **列表渲染**：长列表必须加 `key`，优先使用稳定 ID 而非数组索引
3. **懒加载**：路由级别组件使用 `React.lazy()` + `Suspense`
4. **图片优化**：使用适当尺寸，SVG 图标优先于位图

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

## Git 提交规范

### 提交信息格式

```
<type>(<scope>): <subject>
```

- **type**：`feat`（新功能）、`fix`（修复）、`refactor`（重构）、`perf`（性能）、`test`（测试）、`docs`（文档）、`chore`（杂项）、`style`（格式）、`build`（构建）
- **scope**：`frontend`、`rust`、`python`、`tauri`、`api`、`parser`、`agent`、`deps`
- **subject**：简短描述（不超过 50 字符），使用祈使句现在时，如 "add" 而非 "added"

### 提交范围

- **一个 commit 只做一件事**：不要把功能修改和格式调整混在一起
- **大变更分批次**：如本次操作，按模块/类型分批提交
- **禁止提交**：`node_modules/`、`__pycache__/`、`.env`、编译产物

### 提交前检查清单

- [ ] `cd frontend && npx tsc --noEmit` 零 errors
- [ ] `cd src-tauri && cargo check` 零 errors
- [ ] `uv run ruff check src/` 零 critical errors（迁移期旧代码除外）
- [ ] 不提交 API 密钥或敏感配置
- [ ] `.gitignore` 已覆盖新增产物
- [ ] **CODEMAP.md §7.6 待审核事项**：本次修改涉及的文档/代码问题是否已记录，由人工确认

---

## 测试规范

### Rust 测试

- **测试命名**：`test_{功能}_{场景}`，如 `test_detect_type_pdf`、`test_migration_v0_to_v1`
- **模块测试**：放在被测模块底部的 `#[cfg(test)] mod tests { ... }`
- **依赖注入**：测试中使用内存数据库/临时目录，避免污染真实文件系统
- **Mock**：HTTP 客户端使用 `mockito` 或自定义 stub，避免真实网络请求
- **运行策略**：开发时优先运行目标模块测试，全量测试仅用于 CI/发布前

### Python 测试

- **测试命名**：`test_{功能}_{场景}`，如 `test_llm_chat_stream`、`test_mol_database_search`
- **文件组织**：`tests/unit/` 单元测试，`tests/integration/` 集成测试
- **Fixture**：共享资源（数据库连接、模型实例）使用 `pytest.fixture(scope="session")`
- **覆盖率**：核心逻辑覆盖率目标 ≥ 70%，工具/胶水代码不作硬性要求
- **断言风格**：使用 `assert result.success` 和 `assert result["content"] == "expected"`，避免过度复杂的嵌套断言

### 前端测试

- **单元测试**：工具函数使用 Vitest（尚未配置，后续接入）
- **组件测试**：关键交互组件（Chat、MoleculeLibrary）使用 React Testing Library
- **E2E 测试**：Tauri 应用使用 WebDriver 或手动测试关键路径

### 测试数据

- 使用 `tests/parser_io/` 和 `tests/integration/output/` 存放参考数据
- 测试生成的大型文件（模型权重、缓存）不得提交到 git

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
| 代码逻辑树（最详细） | `CODEMAP.md` | 每个模块的功能、依赖、实现状态 |
| AI 编码指南 | `CLAUDE.md` | 项目概要 + 构建/测试命令 |
| 技术栈详情 | `docs/TECH_STACK.md` | 所有依赖的技术选型、版本、使用场景 |
| 第三方引用 | `docs/REFERENCES.md` | 外部库、论文、数据引用 |
| PDF 迁移规划 | `docs/pipeline-migration-plan.md` | Python→Rust 迁移路线图 |
| 管线重设计 | `docs/pipeline-redesign.md` | 解析管线增量重设计 |
| PDF 提取工作流 | `docs/pdf-extraction-workflow.md` | 端到端 PDF 处理流程 |
| E-SMILES 规范 | `src-tauri/docs/esmiles/` | E-SMILES 格式 + MBForge 集成 |
| LiteParse API | `src-tauri/docs/liteparse/` | LiteParse API 参考存档 |
