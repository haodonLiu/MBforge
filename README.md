# MBForge — Molecular Knowledge Base & AI Workbench

> 面向分子科学/药物发现的桌面端知识库平台。PDF 解析 → 分子提取 → 向量知识库 → AI Agent 对话查询。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![React 19](https://img.shields.io/badge/React-19-blue.svg)](https://react.dev/)
[![Tauri v2](https://img.shields.io/badge/Tauri-v2-orange.svg)](https://tauri.app/)
[![Rust](https://img.shields.io/badge/Rust-2021_edition-red)](https://www.rust-lang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 核心特性

- **Vault 项目管理** — 一个文件夹即一个项目，类似 Obsidian
- **PDF 解析流水线** — Rust 原生解析（lopdf）→ LLM 结构化 → 分子关联 → 摘要 → 向量索引
- **AI Agent 对话** — 本地 Rust ReAct Agent（20+ 工具），支持上下文增强检索
- **分子数据库** — SQLite + FTS5，含 SMILES 属性估算（MW/HBD/HBA/RotBonds）
- **知识库检索** — SQLite FTS5 + semantic_cache 混合搜索 + Rerank 重排序
- **模型服务器** — FastAPI（port 18792），启动预热 + 异步非阻塞，提供 LLM/Embedding/Rerank/VLM/Agent/KB 等 15 个 API 路由
- **模型管理** — 统一模型目录，支持下载/查看/删除，含许可证和大小信息
- **SAR 分析** — 结构-活性关系引擎，支持 Scaffold 聚类、活性悬崖检测
- **MolScribe 集成** — 分子图像 → SMILES 识别（Swin Transformer + Transformer Decoder）
- **多源 PDF 解析** — PyMuPDF / MinerU / LlamaParse / UniParser 四引擎可选
- **LiteParse 就绪** — 文档结构已预留，PDFium 发布后可切换

## 架构概览

```
┌──────────────────────────────────────────────────┐
│  React + Vite + TypeScript  (port 5173)           │
│  ┌──────────┐ ┌──────────┐ ┌───────────────────┐ │
│  │  Chat     │ │Molecule  │ │ Settings / Project│ │
│  │  UI       │ │ Library  │ │ View              │ │
│  └────┬─────┘ └────┬─────┘ └────────┬──────────┘ │
│       │            │                │             │
│  ┌────┴────────────┴────────────────┴──────────┐  │
│  │           tauri-bridge.ts                    │  │
│  │  (window.__TAURI__.invoke → Rust commands)   │  │
│  └────────────────────┬─────────────────────────┘  │
└───────────────────────┼───────────────────────────┘
                        │
┌───────────────────────┼───────────────────────────┐
│  Tauri Shell (Tauri v2 + Rust Agent + Parsers)    │
│  ┌──────────────────┐  ┌──────────────────────┐  │
│  │ src-tauri/src/   │  │  FastAPI Sidecar     │  │
│  │                   │  │  (port 18792)       │  │
│  │  commands/ (11→12) │  │  routers/      (16) │  │
│  │  core/     (32→  ) │  │  models/       (7)  │  │
│  │    memory/          │  │                     │  │
│  │    document/        │  │  ~12,900 行 Python │  │
│  │    molecule/        │  │                     │  │
│  │  parsers/  (12→19) │  │                     │  │
│  │  ~9,800 行 Rust   │  │                     │  │
│  └──────────────────┘  └──────────────────────┘  │
└──────────────────────────────────────────────────┘
```

**双语言分工**: Rust 负责 Agent 循环、PDF 原生解析、SQLite 数据库（molecules.db + vectors.db + semantic_cache.json）、Tauri IPC 命令层；Python 负责 LLM/Embedding/VLM 模型推理、MolScribe 推理、FastAPI REST API。

**性能优化要点**:
- **Rust 共享 HTTP 客户端** — `core/http.rs` 提供 4 个按超时分类的 `LazyLock` 单例，避免每次请求新建连接池
- **Python 异步非阻塞** — 所有模型推理路由通过 `run_in_executor` 包装，不阻塞事件循环
- **启动模型预热** — FastAPI lifespan 在后台线程预加载 LLM/Embedder/Reranker，首次请求零延迟
- **requests.Session 复用** — UniParser 客户端使用持久连接，减少 TCP 握手开销

## 快速开始

### 一键启动（推荐）

```bash
# Windows: 双击 start-dev.bat 或运行 PowerShell 脚本
start-dev.bat        # 批处理脚本
start-dev.ps1        # PowerShell 脚本（支持彩色输出和状态监控）

# Linux/macOS
./start-dev.sh
```

### 手动启动

```bash
# 安装 Python 依赖
uv sync --dev

# 启动模型服务器（终端 1）
uv run uvicorn mbforge.model_server.main:app --host 127.0.0.1 --port 18792

# 启动前端（终端 2）
cd frontend && npm run dev
```

> **注意**: 启动脚本会自动检测并等待服务就绪，然后打开浏览器访问 http://localhost:5173

### 生产构建

```bash
# 打包桌面应用
cd src-tauri && cargo tauri build
```

详见 [ARCHITECTURE.md](ARCHITECTURE.md) 和 [AGENTS.md](AGENTS.md)。

## 项目结构

```
MBForge/
├── src/mbforge/                  # Python 模型服务器 & CLI
│   ├── model_server/             # FastAPI 服务（15 路由）
│   │   ├── main.py               #   入口 + 路由注册
│   │   ├── agent_manager.py      #   Agent 单例管理
│   │   ├── dependencies.py       #   依赖注入
│   │   ├── models/               #   LLM/Embed/Rerank/VLM/MolDet 单例
│   │   └── routers/              #   /api/v1/{llm,embed,agent,kb,molecule,...}
│   ├── core/                     # Python 侧核心
│   │   ├── project.py            #   Vault 项目管理
│   │   ├── knowledge_base.py     #   向量知识库（Rust 侧 FTS5 为主，Python 辅助）
│   │   ├── mol_database.py       #   SQLite 分子数据库（FTS5）
│   │   ├── summarizer.py         #   L0/L1/L2 分层摘要
│   │   ├── document_tree.py      #   文档标题树索引
│   │   └── types.py              #   数据模型定义
│   ├── parsers/                  # Python 侧解析
│   │   ├── pdf_parser.py         #   PDFParserPipeline
│   │   ├── pdf_classifier.py     #   文档类型分类
│   │   ├── ocr_router.py         #   OCR 路由选择
│   │   └── molecule/             #   分子提取管线
│   │       ├── molecule_extractor.py    # 正则 SMILES 提取
│   │       ├── association_engine.py    # 分子-文本关联
│   │       ├── mol_image_pipeline.py    # 图像→SMILES 管线
│   │       └── molscribe_inference/     # MolScribe 推理
│   ├── models/                   # AI 模型抽象层
│   │   ├── base.py               #   BaseLLM/Embedder/Reranker/VLM
│   │   ├── llm.py                #   OpenAI 兼容 LLM
│   │   ├── anthropic_llm.py      #   Anthropic LLM
│   │   ├── embedding.py          #   SentenceTransformer / API
│   │   ├── rerank.py / rerank_qwen3.py
│   │   └── vlm.py                #   视觉语言模型
│   ├── agent/                    # Python 侧工具框架
│   │   ├── executor.py           #   ToolExecutor（10 工具）
│   │   └── optimizations/        #   语义缓存、流式搜索、SPS
│   ├── molecules/schema.py       #   分子数据合约
│   └── cli.py                    #   CLI 入口（mbforge 命令）
│
├── src-tauri/src/                # Rust 代码（Tauri + Agent + Parser）
│   ├── main.rs                   #   Tauri 入口，40+ 命令注册（commands::handler()）
│   ├── lib.rs                    #   模块导出
│   ├── commands/                 #   Tauri 命令层（12 模块）
│   │   ├── mod.rs                #   命令聚合（handler()）
│   │   ├── pdf.rs                #   分类 & 文本提取
│   │   ├── classifier.rs         #   页面/文档分类
│   │   ├── extractor.rs          #   SMILES/活性/关联提取
│   │   ├── molecule.rs           #   分子数据库 CRUD（18 命令）
│   │   ├── mol_engine.rs         #   分子引擎状态管理
│   │   ├── text_ops.rs           #   文本分块
│   │   └── agent.rs              #   Agent 会话管理
│   ├── core/                     #   Rust Agent + 数据层（32 模块，按域分组）
│   │   ├── agent.rs              #   ReAct Agent 循环
│   │   ├── llm.rs                #   LLM HTTP 客户端
│   │   ├── http.rs               #   共享 HTTP 客户端工厂（按超时分类）
│   │   ├── context.rs            #   分层会话上下文
│   │   ├── executor/             #   ToolExecutor（25+ 工具，按类别拆分）
│   │   │   ├── mod.rs            #     协调入口
│   │   │   ├── fs.rs             #     文件系统工具
│   │   │   ├── kb.rs             #     知识库搜索工具
│   │   │   ├── document.rs       #     文档摘要/结构工具
│   │   │   ├── molecule.rs       #     分子分析工具
│   │   │   └── literature.rs     #     文献检索工具
│   │   ├── molecule/             #   分子相关模块（已分组）
│   │   │   ├── molecule_store.rs #     SQLite + FTS5 分子数据库
│   │   │   ├── molecule_db.rs    #     分子关系数据库
│   │   │   ├── molecule_dedup.rs #     分子去重
│   │   │   ├── molecule_cluster.rs #   分子聚类
│   │   │   └── molecule_engine.rs #    统一分子分析引擎
│   │   ├── memory/               #   记忆与轨迹（已分组）
│   │   │   ├── memory.rs         #     6 分类持久记忆
│   │   │   ├── trajectory.rs     #     轨迹跟踪
│   │   │   ├── skills.rs         #     技能管理
│   │   │   └── pending.rs        #     待处理提取
│   │   ├── document/             #   文档处理（已分组）
│   │   │   ├── knowledge_base.rs #     FTS5 知识库
│   │   │   ├── document_tree.rs  #     文档结构树
│   │   │   ├── summary.rs        #     文档摘要持久化
│   │   │   ├── semantic_cache.rs #     三级语义缓存
│   │   │   └── stream_search.rs  #     流式搜索
│   │   ├── tools.rs              #   工具注册表
│   │   ├── sar_query.rs          #   SAR 查询引擎
│   │   ├── markush.rs            #   E-SMILES Markush 分析
│   │   ├── arxiv.rs              #   arXiv/PMC 论文 API
│   │   └── project.rs            #   项目文档索引
│   └── parsers/                  #   Rust PDF 解析（19 模块）
│       ├── doc_types.rs          #   管线共享数据结构（原 types.rs）
│       ├── pipeline.rs           #   统一解析管线入口（Stage 0-7）
│       │   └── extract.rs        #     Stage 0: 分类与提取
│       │   └── helpers.rs        #     record 映射 + section 文本提取
│       │   └── merge.rs          #     Stage 3: 合并 + SAR + 专利增强
│       ├── images.rs             #   lopdf 图像提取
│       ├── association.rs        #   分子-文本关联引擎
│       ├── keywords.rs           #   关键词 & 实体提取
│       ├── intent.rs             #   意图路由（LLM 分类）
│       ├── post_process.rs       #   LLM 结构化后处理
│       ├── report.rs             #   Markdown 报告生成
│       ├── vlm_chem.rs           #   VLM 化学结构识别
│       ├── uniparser.rs          #   UniParser API 客户端
│       ├── llama_parse.rs        #   LlamaParse API 客户端
│       ├── mineru.rs             #   MinerU API 客户端
│       ├── molecule_extractor.rs #   专利命名化合物提取
│       ├── claim_parser.rs       #   专利 Claims 解析
│       └── claim_policy.rs       #   专利范围匹配
│
├── frontend/                     # React + Vite 前端
│   ├── src/
│   │   ├── App.tsx               #   路由入口
│   │   ├── api/                  #   HTTP + Tauri 桥接
│   │   │   ├── client.ts         #   HTTP 客户端（fetchJson + sseStream）
│   │   │   ├── tauri/            #   Tauri invoke 子模块（按域拆分）
│   │   │   │   ├── _utils.ts     #     通用工具（listen/unlisten）
│   │   │   │   ├── agent.ts      #     Agent 会话
│   │   │   │   ├── kb.ts         #     知识库
│   │   │   │   ├── molecule.ts   #     分子数据库
│   │   │   │   ├── pdf.ts        #     PDF 操作
│   │   │   │   ├── project.ts    #     项目管理
│   │   │   │   ├── text.ts       #     文本处理
│   │   │   │   └── environment.ts #    环境信息
│   │   │   ├── settings.ts       #   设置 API
│   │   │   └── download.ts       #   模型下载 API
│   │   ├── components/           #   ~70 组件（页面级 + 原子 + 子模块）
│   │   │   ├── Chat.tsx          #   对话界面
│   │   │   ├── MoleculeLibrary.tsx
│   │   │   ├── ProjectView.tsx   #   项目仪表盘（协调层）
│   │   │   ├── project/          #   项目子组件
│   │   │   │   ├── PdfViewer.tsx #     PDF 阅读器 + 分子检测
│   │   │   │   └── ProjectDashboard.tsx # 文档列表/统计/索引
│   │   │   ├── Search.tsx
│   │   │   ├── Workflow.tsx
│   │   │   ├── ui/               #   ~40 原子组件
│   │   │   └── ...
│   │   ├── context/              #   React Context（AppContext 全局状态）
│   │   ├── hooks/                #   React Hooks
│   │   └── types/                #   TypeScript 类型
│   └── vite.config.ts            #   Vite 配置（API 代理 18792）
│
├── setup/                        # 一键配置脚本
│   ├── index.sh / index.bat      #   交互式安装
│   ├── modules/                  #   8 步配置
│   └── MolScribe/                #   MolScribe 完整代码
│
├── tests/                        # 测试
│   ├── unit/                     #   Python 测试（83 个）
│   └── Rust 侧测试               #   ~226 个（src-tauri）
│
├── docs/                         # 项目文档
│   ├── ARCHITECTURE.md           #   系统架构
│   ├── API.md                    #   公共 API 参考
│   ├── TECH_STACK.md             #   技术栈
│   ├── DEVELOPMENT.md            #   开发指南
│   ├── pipeline-migration-plan.md # PDF 解析 Python→Rust 迁移规划
│   ├── pipeline-redesign.md      #   管线增量重设计
│   ├── pdf-extraction-workflow.md # PDF 提取工作流
│   └── pdf-pipeline-test/        #   管线测试用例
│
├── src-tauri/docs/               # Rust 侧本地文档
│   ├── esmiles/                  #   E-SMILES 格式规范 + MBForge 集成
│   └── liteparse/                #   LiteParse API 参考（官网存档）
│
├── CLAUDE.md                     # AI 编码助手指南
└── AGENTS.md                     # Agent 配置
```

## 技术栈

| 类别 | 技术 | 行数 |
|------|------|------|
| **Rust 核心** | Tauri v2, lopdf, rusqlite, serde, regex, reqwest, tokio | ~9,800 |
| **Python 服务** | FastAPI, uvicorn, PyMuPDF, sentence-transformers | ~12,900 |
| **前端** | React 19, TypeScript, Vite 6 | — |
| **化学信息学** | RDKit (Python), MolScribe (Swin + Transformer), E-SMILES | — |
| **PDF 解析** | lopdf (Rust), PyMuPDF, MinerU API, LlamaParse, UniParser | — |
| **包管理** | uv workspace (Python) + Cargo (Rust) | — |
| **测试** | Rust: `cargo test` (226), Python: `pytest` (83) | — |

## 测试

```bash
# Rust 测试（226 个）
cd src-tauri && cargo test

# Python 测试（83 个）
uv run pytest tests/ -v

# 代码检查
uv run ruff check src/ && uv run ruff format src/ --check
```

## 文档索引

| 文档 | 位置 |
|------|------|
| 系统架构 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Agent 规范 | [AGENTS.md](AGENTS.md) |
| 技术栈 | [docs/TECH_STACK.md](docs/TECH_STACK.md) |
| 编码指南 | [CLAUDE.md](CLAUDE.md) |
| 第三方引用 | [docs/REFERENCES.md](docs/REFERENCES.md) |
| PDF 迁移规划 | [docs/pipeline-migration-plan.md](docs/pipeline-migration-plan.md) |
| 管线重设计 | [docs/pipeline-redesign.md](docs/pipeline-redesign.md) |
| E-SMILES 规范 | [src-tauri/docs/esmiles/](src-tauri/docs/esmiles/) |
| LiteParse API | [src-tauri/docs/liteparse/](src-tauri/docs/liteparse/) |
| 编码指南 | [CLAUDE.md](CLAUDE.md) |

## 许可

MIT License
