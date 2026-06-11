# MBForge — Molecular Knowledge Base & AI Workbench

> 面向分子科学/药物发现的桌面端知识库平台。PDF 解析 → 分子提取 → 向量知识库 → AI Agent 对话查询。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![React 19](https://img.shields.io/badge/React-19-blue.svg)](https://react.dev/)
[![Tauri v2](https://img.shields.io/badge/Tauri-v2-orange.svg)](https://tauri.app/)
[![Rust](https://img.shields.io/badge/Rust-2021_edition-red)](https://www.rust-lang.org/)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](LICENSE)

## 核心特性

- **Vault 项目管理** — 一个文件夹即一个项目，类似 Obsidian
- **PDF 解析流水线** — Rust 原生解析（lopdf）→ LLM 结构化 → 分子关联 → 摘要 → 向量索引
- **AI Agent 对话** — 本地 Rust ReAct Agent（20+ 工具），支持上下文增强检索
- **分子数据库** — SQLite + FTS5，含 SMILES 属性估算（MW/HBD/HBA/RotBonds）
- **知识库检索** — SQLite FTS5 + semantic_cache 混合搜索 + Rerank 重排序
- **模型服务器** — FastAPI（port 18792），启动预热 + 异步非阻塞，提供 Embedding / Rerank / MolDet / MolScribe 端点
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
│  │  commands/ (18)   │  │  backends/     (5)  │  │
│  │  core/     (74)   │  │  server.py          │  │
│  │    agent/          │  │                     │  │
│  │    chem/           │  │  Qwen3-Embed /      │  │
│  │    document/       │  │  Qwen3-Rerank /     │  │
│  │    molecule/       │  │  MolDet / MolScribe │  │
│  │  parsers/  (27)   │  │                     │  │
│  └──────────────────┘  └──────────────────────┘  │
└──────────────────────────────────────────────────┘
```

**双语言分工**: 
Rust 负责 Agent 循环、PDF 原生解析、SQLite 数据库（molecules.db + vectors.db + semantic_cache.json）、Tauri IPC 命令层、API 模型调用（OpenAI/Anthropic 等）；
Python 负责本地模型推理（Embedding、Rerank、MolDet、MolScribe）、FastAPI REST API。

**性能优化要点**:
- **Rust 共享 HTTP 客户端** — `core/http.rs` 提供 4 个按超时分类的 `LazyLock` 单例，避免每次请求新建连接池
- **Python 异步非阻塞** — 所有模型推理路由通过 `run_in_executor` 包装，不阻塞事件循环
- **启动模型预热** — FastAPI lifespan 在后台线程预加载 Embedding/Rerank/MolDet/MolScribe，首次请求零延迟
- **requests.Session 复用** — UniParser 客户端使用持久连接，减少 TCP 握手开销

## 快速开始

### 手动启动

```bash
# 安装 Python 依赖
uv sync --dev

# 启动模型服务器（终端 1）
uv run uvicorn mbforge.server:app --host 127.0.0.1 --port 18792

# 启动前端（终端 2）
cd frontend && npm run dev
```

访问 http://localhost:5173

### 生产构建

```bash
# 打包桌面应用
cd src-tauri && cargo tauri build
```

详见 [AGENTS.md](AGENTS.md)。

## 项目结构

```
MBForge/
├── src/mbforge/                  # Python 模型服务器 & CLI
│   ├── server.py                 #   FastAPI 入口（端点内联，lifespan 预热）
│   ├── backends/                 #   本地模型后端（5 个固定后端）
│   │   ├── qwen3_embed.py        #   Qwen3-Embedding
│   │   ├── qwen3_rerank.py       #   Qwen3-Reranker
│   │   ├── molscribe.py          #   MolScribe 分子图像识别
│   │   ├── moldet.py             #   MolDet 分子检测（YOLO）
│   │   └── moldet_coref.py       #   MolDet Coref 关联
│   ├── core/                     #   Python 侧核心
│   │   └── resource_manager.py   #   资源管理 + ModelScope 下载
│   ├── parsers/                  #   Python 侧解析（MolScribe 推理引擎）
│   │   └── molecule/
│   │       └── molscribe_inference/  #   Swin Transformer + Transformer Decoder
│   └── utils/                    #   配置、常量、辅助、日志
│
├── src-tauri/src/                # Rust 代码（Tauri + Agent + Parser）
│   ├── main.rs                   #   Tauri 入口，命令注册（commands::handler()）
│   ├── lib.rs                    #   模块导出
│   ├── commands/                 #   Tauri 命令层（17 模块）
│   │   ├── mod.rs                #   命令聚合（handler()）
│   │   ├── agent.rs              #   Agent 会话
│   │   ├── classifier.rs         #   页面/文档分类
│   │   ├── detection_cache.rs    #   检测缓存管理
│   │   ├── extractor.rs          #   SMILES/活性/关联提取
│   │   ├── file_ops.rs           #   文件操作
│   │   ├── llm.rs                #   LLM 调用
│   │   ├── mol_engine.rs         #   分子引擎状态
│   │   ├── mol_store.rs          #   分子存储
│   │   ├── molecode.rs           #   MoleCode 生成
│   │   ├── molecule.rs           #   分子数据库 CRUD
│   │   ├── notes.rs              #   笔记管理
│   │   ├── pdf.rs                #   PDF 操作
│   │   ├── project_ops.rs        #   项目操作
│   │   ├── settings.rs           #   设置管理
│   │   ├── sidecar.rs            #   Sidecar 管理
│   │   └── text_ops.rs           #   文本处理
│   ├── core/                     #   Rust Agent + 数据层（按域分组）
│   │   ├── agent/                #   Agent 子系统（rig 工具 / ReAct / memory）
│   │   ├── chem/                 #   化学信息学（SMILES/E-SMILES/MoleCode/Markush）
│   │   ├── config/               #   配置与常量
│   │   ├── document/             #   文档处理（KB/Tree/Summary/SemanticCache）
│   │   ├── models/               #   模型目录管理（下载/状态/解析）
│   │   ├── molecule/             #   分子模块（Store/DB/Dedup/Cluster/Engine）
│   │   ├── project/              #   项目与笔记
│   │   ├── vector/               #   向量存储与 Embedding
│   │   ├── db.rs                 #   统一 SQLite 数据库连接
│   │   ├── error.rs              #   错误类型
│   │   ├── helpers.rs            #   通用辅助函数
│   │   ├── http.rs               #   共享 HTTP 客户端工厂
│   │   ├── sidecar_client.rs     #   Sidecar HTTP 客户端
│   │   └── types.rs              #   共享类型
│   └── parsers/                  #   Rust PDF 解析管线
│       ├── doc_types.rs          #   管线共享数据结构
│       ├── pipeline.rs           #   统一解析管线入口
│       │   ├── extract.rs        #   分类与提取逻辑
│       │   ├── helpers.rs        #   record 映射 + 文本提取
│       │   ├── markdown_augment.rs # Markdown 增强
│       │   └── merge.rs          #   合并 + SAR + 专利增强
│       ├── chem/                 #   化学解析子模块
│       │   ├── association.rs    #   分子-文本关联引擎
│       │   ├── chem_validate.rs  #   化学结构验证
│       │   ├── claim_parser.rs   #   专利 Claims 解析
│       │   ├── claim_policy.rs   #   专利范围匹配
│       │   ├── label_assoc.rs    #   标签关联
│       │   ├── molecule_extractor.rs # 专利命名化合物提取
│       │   └── vlm_chem.rs       #   VLM 化学识别
│       ├── pdf/                  #   PDF 解析客户端
│       │   ├── images.rs         #   lopdf 图像提取
│       │   ├── liteparse.rs      #   LiteParse 客户端
│       │   ├── llama_parse.rs    #   LlamaParse API 客户端
│       │   ├── mineru.rs         #   MinerU API 客户端
│       │   └── uniparser.rs      #   UniParser API 客户端
│       ├── structure/            #   文档结构处理
│       │   ├── intent.rs         #   意图路由（LLM 分类）
│       │   ├── post_process.rs   #   LLM 后处理 / JSON 修复
│       │   ├── report.rs         #   Markdown 报告生成
│       │   └── sections.rs       #   章节构建与语义分块
│       └── keywords.rs           #   关键词与实体提取
│
├── frontend/                     # React + Vite 前端
│   ├── src/
│   │   ├── App.tsx               #   路由入口
│   │   ├── api/                  #   HTTP + Tauri 桥接
│   │   │   ├── tauri-events.ts
│   │   │   └── tauri/            #   Tauri invoke 子模块（按域拆分）
│   │   │       ├── _utils.ts     #     通用工具
│   │   │       ├── agent.ts      #     Agent 会话
│   │   │       ├── audit.ts      #     审计日志
│   │   │       ├── detection_cache.ts # 检测缓存
│   │   │       ├── download.ts   #     模型下载
│   │   │       ├── environment.ts #    环境信息
│   │   │       ├── kb.ts         #     知识库
│   │   │       ├── molecule.ts   #     分子数据库
│   │   │       ├── notes.ts      #     笔记管理
│   │   │       ├── pdf.ts        #     PDF 操作
│   │   │       ├── project.ts    #     项目管理
│   │   │       ├── sar.ts        #     SAR 分析
│   │   │       ├── settings.ts   #     设置管理
│   │   │       ├── sidecar.ts    #     Sidecar 管理
│   │   │       └── text.ts       #     文本处理
│   │   ├── components/           #   组件（页面级 + 原子 + 子模块）
│   │   │   ├── Chat.tsx          #   对话界面
│   │   │   ├── MoleculeLibrary.tsx
│   │   │   ├── ProjectView.tsx   #   项目仪表盘
│   │   │   ├── project/          #   项目子组件
│   │   │   │   ├── PdfViewer.tsx
│   │   │   │   └── ProjectDashboard.tsx
│   │   │   ├── molecule/         #   分子相关组件
│   │   │   ├── notes/            #   笔记编辑器组件
│   │   │   ├── sar/              #   SAR 分析组件
│   │   │   ├── settings/         #   设置组件
│   │   │   ├── ui/               #   原子组件
│   │   │   └── ...
│   │   ├── context/              #   React Context
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
│   ├── unit/                     #   Python 单元测试
│   └── integration/              #   集成测试
│
├── docs/                         # 项目文档
│   ├── esmiles-spec.md           #   E-SMILES 格式规范
│   ├── molecode-spec.md          #   MoleCode 图语法规范
│   ├── pipeline-redesign.md      #   管线增量重设计
│   ├── TECH_STACK.md             #   技术栈
│   └── archive/                  #   归档文档
│
├── src-tauri/docs/               # Rust 侧本地文档
│   ├── esmiles/                  #   E-SMILES 格式规范 + MBForge 集成
│   └── liteparse/                #   LiteParse API 参考（官网存档）
│
├── CLAUDE.md                     # AI 编码助手指南
└── AGENTS.md                     # Agent 配置
```

## 技术栈

| 类别 | 技术 |
|------|------|
| **Rust 核心** | Tauri v2, lopdf, rusqlite, serde, regex, reqwest, tokio |
| **Python 服务** | FastAPI, uvicorn, PyMuPDF, sentence-transformers |
| **前端** | React 19, TypeScript, Vite 6 |
| **化学信息学** | chematic (Rust), RDKit (Python fallback), MolScribe (Swin + Transformer), E-SMILES |
| **PDF 解析** | lopdf (Rust), PyMuPDF, MinerU API, LlamaParse, UniParser |
| **包管理** | uv workspace (Python) + Cargo (Rust) |
| **测试** | Rust: `cargo test`, Python: `pytest` |

## 测试

```bash
# Rust 测试
cd src-tauri && cargo test

# Python 测试
uv run pytest tests/ -v

# 代码检查
uv run ruff check src/ && uv run ruff format src/ --check
```

## 文档索引

| 文档 | 位置 | 说明 |
|------|------|------|
| 项目入口 | [README.md](README.md) | 人类用户快速开始 |
| Agent 规范 + 架构 | [AGENTS.md](AGENTS.md) | AI 编码助手操作手册 |
| 编码指南 | [CLAUDE.md](CLAUDE.md) | Claude 上下文 + 架构速查 |
| **文档治理规范** | [`.claude/documentation-governance.md`](.claude/documentation-governance.md) | 描述文件分工与回刷机制 |
| E-SMILES 规范 | [docs/esmiles-spec.md](docs/esmiles-spec.md) | 分子表示规范 |
| MoleCode 规范 | [docs/molecode-spec.md](docs/molecode-spec.md) | 图语法规范 |
| 技术栈 | [docs/TECH_STACK.md](docs/TECH_STACK.md) | 依赖选型详情 |
| 管线重设计 | [docs/pipeline-redesign.md](docs/pipeline-redesign.md) | 解析管线增量设计 |

## 许可

CC BY-NC-SA 4.0 (非商用，禁止商业使用)
