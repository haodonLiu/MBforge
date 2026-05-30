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
- **知识库检索** — ChromaDB 语义搜索 + Rerank 重排序
- **模型服务器** — FastAPI（port 18792），提供 LLM/Embedding/Rerank/VLM/Agent/KB 等 15 个 API 路由
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
│  │  commands/  (6)   │  │  routers/      (15) │  │
│  │  core/     (16)   │  │  models/       (5)  │  │
│  │  parsers/  (12)   │  │  agent/        (4)  │  │
│  │                   │  │  parsers/      (8)  │  │
│  │  ~9,681 行 Rust   │  │  ~12,882 行 Python │  │
│  └──────────────────┘  └──────────────────────┘  │
└──────────────────────────────────────────────────┘
```

**双语言分工**: Rust 负责 Agent 循环、PDF 原生解析、分子数据库、SQLite 持久化；Python 负责 LLM/Embedding/VLM 模型推理、ChromaDB 向量库、MolScribe 推理、FastAPI REST API。

## 快速开始

```bash
# 安装 Python 依赖
uv sync --dev

# 启动模型服务器（终端 1）
uv run uvicorn mbforge.model_server.main:app --host 127.0.0.1 --port 18792

# 启动前端（终端 2）
cd frontend && npm run dev
```

### 生产构建

```bash
# 打包桌面应用
cd src-tauri && cargo tauri build
```

详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 和 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

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
│   │   ├── knowledge_base.py     #   ChromaDB 向量知识库
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
│   ├── main.rs                   #   Tauri 入口，25+ 命令注册
│   ├── lib.rs                    #   模块导出
│   ├── commands/                 #   Tauri 命令层（6 模块）
│   │   ├── pdf.rs                #   分类 & 文本提取
│   │   ├── classifier.rs         #   页面/文档分类
│   │   ├── extractor.rs          #   SMILES/活性/关联提取
│   │   ├── molecule.rs           #   分子数据库 CRUD（18 命令）
│   │   ├── text_ops.rs           #   文本分块
│   │   └── agent.rs              #   Agent 会话管理
│   ├── core/                     #   Rust Agent + 数据层（16 模块）
│   │   ├── agent.rs              #   ReAct Agent 循环
│   │   ├── llm.rs                #   LLM HTTP 客户端
│   │   ├── context.rs            #   分层会话上下文
│   │   ├── executor.rs           #   ToolExecutor（20+ 工具）
│   │   ├── molecule_store.rs     #   分子 SQLite 数据库
│   │   ├── molecule_db.rs        #   分子关系数据库
│   │   ├── molecule_dedup.rs     #   分子去重
│   │   ├── molecule_cluster.rs   #   分子聚类
│   │   ├── sar_query.rs          #   SAR 查询引擎
│   │   ├── memory.rs             #   6 分类持久记忆
│   │   ├── trajectory.rs         #   轨迹跟踪
│   │   ├── skills.rs             #   技能管理
│   │   ├── tools.rs              #   工具注册表
│   │   ├── summary.rs            #   文档摘要持久化
│   │   ├── pending.rs            #   待处理提取
│   │   └── project.rs            #   项目文档索引
│   └── parsers/                  #   Rust PDF 解析（12 模块）
│       ├── types.rs              #   共享数据结构
│       ├── pipeline.rs           #   统一解析管线（Stage 1-6）
│       ├── images.rs             #   lopdf 图像提取
│       ├── association.rs        #   分子-文本关联引擎
│       ├── keywords.rs           #   关键词 & 实体提取
│       ├── intent.rs             #   意图路由（LLM 分类）
│       ├── post_process.rs       #   LLM 结构化后处理
│       ├── report.rs             #   Markdown 报告生成
│       ├── vlm_chem.rs           #   VLM 化学结构识别
│       ├── uniparser.rs          #   UniParser API 客户端
│       ├── llama_parse.rs        #   LlamaParse API 客户端
│       └── mineru.rs             #   MinerU API 客户端
│
├── frontend/                     # React + Vite 前端
│   ├── src/
│   │   ├── App.tsx               #   路由入口
│   │   ├── api/                  #   HTTP + Tauri 桥接
│   │   │   ├── client.ts         #   HTTP 客户端
│   │   │   ├── tauri-bridge.ts   #   Tauri invoke
│   │   │   └── settings.ts       #   设置 API
│   │   ├── components/           #   14 组件
│   │   │   ├── Chat.tsx          #   对话界面
│   │   │   ├── MoleculeLibrary.tsx
│   │   │   ├── PDFViewer.tsx
│   │   │   ├── Search.tsx
│   │   │   ├── Workflow.tsx
│   │   │   └── ...
│   │   ├── hooks/                #   React Hooks
│   │   └── types/                #   TypeScript 类型
│   └── vite.config.ts            #   Vite 配置（API 代理 18792）
│
├── rust/                         # PyO3 加速模块（~700 行）
│   └── src/lib.rs                #   高精度 Tanimoto 矩阵
│
├── setup/                        # 一键配置脚本
│   ├── index.sh / index.bat      #   交互式安装
│   ├── modules/                  #   8 步配置
│   └── MolScribe/                #   MolScribe 完整代码
│
├── tests/                        # 测试
│   ├── unit/                     #   Python 测试（28 个）
│   └── Rust 侧测试               #   99 个（src-tauri）
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
| **Rust 核心** | Tauri v2, lopdf, rusqlite, serde, regex, tokio | ~9,700 |
| **Python 服务** | FastAPI, uvicorn, ChromaDB, PyMuPDF, sentence-transformers | ~12,900 |
| **前端** | React 19, TypeScript, Vite 6 | — |
| **化学信息学** | RDKit (Python), MolScribe (Swin + Transformer), E-SMILES | — |
| **PDF 解析** | lopdf (Rust), PyMuPDF, MinerU API, LlamaParse, UniParser | — |
| **包管理** | uv workspace (Python) + Cargo (Rust) | — |
| **测试** | Rust: `cargo test` (99), Python: `pytest` (28) | — |

## 测试

```bash
# Rust 测试（99 个）
cd src-tauri && cargo test

# Python 测试（28 个）
uv run pytest tests/ -v

# 代码检查
uv run ruff check src/ && uv run ruff format src/ --check
```

## 文档索引

| 文档 | 位置 |
|------|------|
| 系统架构 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 公共 API | [docs/API.md](docs/API.md) |
| 技术栈 | [docs/TECH_STACK.md](docs/TECH_STACK.md) |
| 开发指南 | [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) |
| PDF 迁移规划 | [docs/pipeline-migration-plan.md](docs/pipeline-migration-plan.md) |
| 管线重设计 | [docs/pipeline-redesign.md](docs/pipeline-redesign.md) |
| E-SMILES 规范 | [src-tauri/docs/esmiles/](src-tauri/docs/esmiles/) |
| LiteParse API | [src-tauri/docs/liteparse/](src-tauri/docs/liteparse/) |
| 编码指南 | [CLAUDE.md](CLAUDE.md) |

## 许可

MIT License
