# MBForge — Molecular Knowledge Base & AI Workbench

[English](#english) | [中文](#中文)

---

# English

> **Bringing molecular literature to life.** MBForge is a desktop AI workbench that transforms PDF papers into searchable, reasoning-capable molecular knowledge bases with natural language query support.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![React 19](https://img.shields.io/badge/React-19-blue.svg)](https://react.dev/)
[![Tauri v2](https://img.shields.io/badge/Tauri-v2-orange.svg)](https://tauri.app/)
[![Rust](https://img.shields.io/badge/Rust-2021_edition-red)](https://www.rust-lang.org/)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](LICENSE)

## What is MBForge?

MBForge (Molecular Knowledge Base) is a desktop application for **drug discovery** and **molecular science** researchers. It solves a critical pain point:

> **Molecular structures and activity data scattered across PDFs are tedious to compile manually and difficult to query or reason about.**

### Core Workflow

```
PDF Documents
    ↓ Intelligent Parsing
Structured Data (Compounds + Activity Data + Findings)
    ↓ Molecule Ingestion
Local Knowledge Base (SQLite + Vector Index)
    ↓ AI Conversation
Natural Language Query + Reasoning Analysis
```

## Key Features

### Smart PDF Parsing

- **Multi-engine Support**: Rust native (lopdf) / PyMuPDF / MinerU / LlamaParse / UniParser
- **Intent-driven**: Extract only what you need (e.g., "extract activity data from TABLE 1"), skip irrelevant sections
- **Image Molecule Recognition**: YOLO detection + MolScribe (Swin Transformer) converts chemical structure images to SMILES
- **Structured Output**: Compounds, activity data, key findings, uncertainties — auto-generated Markdown reports

### AI Agent Conversation

- **Local ReAct Agent**: 20+ tools for knowledge base retrieval, molecule queries, file operations
- **Context Enhancement**: Auto-retrieves relevant literature and molecule data for precise answers
- **Multi-turn Memory**: Persistent conversation history for complex reasoning tasks
- **Multi-LLM Support**: OpenAI / Anthropic / Ollama (local models)

### Molecule Database

- **Three-layer Representation**:
  - **SMILES**: Source of truth, RDKit/chematic compatible
  - **E-SMILES**: Semantic extension with Markush structures and R-group labels
  - **MoleCode**: LLM-friendly Mermaid graph syntax with explicit topology
- **Smart Deduplication**: Tanimoto similarity + auto-clustering
- **Property Estimation**: Molecular weight, H-bond donors/acceptors, rotatable bonds
- **Full-text Search**: FTS5 + vector semantic + Rerank re-ranking

### SAR Analysis

- **Structure-Activity Relationships**: Scaffold clustering, activity cliff detection
- **R-group Analysis**: Visualize substituent positions vs. activity correlation
- **Correction Workflow**: OCR result human review and correction

### Project Management

- **Vault Mode**: One folder = one project, Obsidian-style workflow
- **Unified Storage**: molecules.db + vectors.db + semantic_cache.json
- **Model Management**: Unified directory with download/view/delete, license info included
- **Audit Log**: All operations are traceable

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  React + Vite + TypeScript  (port 5173)                      │
│  ┌──────────┐ ┌──────────────┐ ┌─────────────────────────┐  │
│  │  Chat    │ │  Molecule    │ │  Settings / Project     │  │
│  │  Agent   │ │  Library     │ │  View / SAR Analysis    │  │
│  └────┬─────┘ └──────┬───────┘ └───────────┬─────────────┘  │
│       │              │                     │                │
│  ┌────┴──────────────┴─────────────────────┴─────────────┐  │
│  │              api/tauri/index.ts                        │  │
│  │    (window.__TAURI__.invoke → Rust commands)           │  │
│  └───────────────────────┬───────────────────────────────┘  │
└──────────────────────────┼──────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────┐
│  Tauri Shell (Tauri v2 + Rust Core + Python Sidecar)        │
│  ┌────────────────────┐  ┌──────────────────────────────┐  │
│  │  src-tauri/crates/ │  │  FastAPI Sidecar             │  │
│  │                    │  │  (port 18792)                 │  │
│  │  mbforge-app/      │  │  ┌────────────────────────┐  │  │
│  │    commands/ (~30) │  │  │ Qwen3-Embedding       │  │  │
│  │  ────────────────  │  │  │ Qwen3-Reranker        │  │  │
│  │  mbforge-domain/   │  │  │ MolDet (YOLO)         │  │  │
│  │    document/       │  │  │ MolScribe (Swin+TR)   │  │  │
│  │    molecule/       │  │  │ Zvec (dense+FTS)      │  │  │
│  │    project/        │  │  └────────────────────────┘  │  │
│  │    vector/         │  │                              │  │
│  │  mbforge-pipeline/ │  │                              │  │
│  │    pipeline/       │  │                              │  │
│  │    structure/      │  │                              │  │
│  │    pdf/, ocr/, chem/│  │                              │  │
│  │  mbforge-infra/    │  │                              │  │
│  │  mbforge-chem/     │  │                              │  │
│  └────────────────────┘  └──────────────────────────────┘  │
```

### Dual-language Architecture

| Layer | Language | Responsibility |
|-------|----------|----------------|
| **Rust Core** | Rust | Agent loop, PDF native parsing, SQLite database, Tauri IPC command layer, API model calls |
| **Python Service** | Python | Local model inference (Embedding, Rerank, MolDet, MolScribe, Zvec dense+FTS), FastAPI REST API |
| **Frontend** | TypeScript | React components, page routing, state management, Tauri bridging |

### Performance Optimizations

- **Rust Shared HTTP Client**: 4 timeout-categorized LazyLock singletons avoid connection pool creation per request
- **Python Async Non-blocking**: All model inference routes wrapped with `run_in_executor`
- **Startup Model Preheating**: FastAPI lifespan preloads Embedding/Rerank/MolDet/MolScribe in background threads
- **requests.Session Reuse**: UniParser client uses persistent connections

## Quick Start

> **Note:** The legacy one-click installer (`setup/index.sh` / `setup\index.bat`) was retired when the project moved to a 5-crate Rust workspace and a single Python sidecar. Use the **Manual Start** below — it is the supported path as of 2026-06-25.

### Manual Start

```bash
# Install Python dependencies
uv sync --dev

# Start model server (Terminal 1)
uv run uvicorn mbforge.server:app --host 127.0.0.1 --port 18792

# Start frontend (Terminal 2)
cd frontend && npm run dev
```

Visit http://localhost:5173

### Production Build

```bash
# Package desktop application
cd src-tauri && cargo tauri build
```

## Tech Stack

| Category | Technology | Version | Purpose |
|----------|-----------|---------|---------|
| **Rust Core** | Tauri v2, lopdf, rusqlite, reqwest, tokio | 2 | Desktop shell, PDF parsing, database, HTTP, async |
| **Python Service** | FastAPI, uvicorn, PyTorch (CUDA 12.8) | ≥0.115, ≥2.6 | REST API, model inference |
| **Frontend** | React 19, TypeScript 6, Vite 8 | 19, 6, 8 | UI framework, type system, build tool |
| **Cheminformatics** | chematic (Rust), RDKit (Python), MolScribe | — | Molecule parsing, fingerprints, image recognition |
| **AI/ML** | sentence-transformers, ultralytics (YOLO) | ≥2.5, ≥8.3 | Embedding, molecule detection |
| **PDF Parsing** | lopdf (Rust), PyMuPDF, MinerU, LlamaParse, UniParser | — | Multi-engine document parsing |
| **Package Manager** | uv (Python), Cargo (Rust), npm (frontend) | — | Dependency management |

## Testing

```bash
# Rust tests
cd src-tauri && cargo test

# Python tests
uv run pytest tests/ -v

# Code check
uv run ruff check src/ && uv run ruff format src/ --check
```

## Known Limitations

> We believe in transparency. Here are the current limitations we're actively working on:

### Architecture Debt

1. **chem_validate.rs / core/chem.rs Overlap**: Duplicate chemical validation logic needs consolidation
2. **vector_store.rs Interface Redundancy**: Multiple vector store implementations with overlapping APIs
3. **std::sync::Mutex in Async Context**: Blocking mutexes in async code paths causing potential deadlocks

### Performance Bottlenecks

1. **27-minute Pipeline**: LLM calls are serial, causing long processing times for complex documents
2. **No Cost Tracking**: No budget enforcement or cost monitoring for LLM API usage
3. **Python Sidecar Single-process**: No connection pool or graceful degradation for model server

### Feature Gaps

1. **chematic Dependency**: Git-based dependency without stable release tags
2. **tracing Coverage**: Incomplete observability across cross-boundary calls
3. **constants.rs Generation**: Code generation mechanism partially broken

### UI/UX Issues

1. **Mobile Support**: No responsive design for tablet/mobile viewing
2. **Collaboration**: No real-time multi-user collaboration features
3. **Export Formats**: Limited export options beyond Markdown

## Roadmap

### Q3 2026 — Stability & Performance

- [ ] Merge overlapping chem validation modules
- [ ] Implement parallel LLM calls in pipeline (target: <5 min)
- [ ] Add BudgetEnforcer for cost tracking
- [ ] Fix vector_store interface redundancy
- [ ] Expand tracing to all cross-boundary calls

### Q4 2026 — Enhanced AI Capabilities

- [ ] Multi-modal RAG (text + images + molecular structures)
- [ ] Agent workflow automation (scheduled tasks, batch processing)
- [ ] Custom tool creation UI for domain-specific operations
- [ ] Integration with external databases (ChEMBL, PubChem)

### 2027 — Platform Evolution

- [ ] Mobile/tablet companion app
- [ ] Real-time collaboration (multi-user knowledge base)
- [ ] Plugin system for community extensions
- [ ] Cloud sync with end-to-end encryption
- [ ] Advanced SAR visualization (3D molecular views)

## Contributing

Contributions are welcome! Please see [AGENTS.md](AGENTS.md) for development guidelines.

### Commit Convention

```
<type>(<scope>): <subject>

Types: feat | fix | refactor | perf | test | docs | chore
Scopes: frontend | rust | python | tauri | api | parser | agent | deps
```

## Documentation

| Document | Location | Description |
|----------|----------|-------------|
| **Project Entry** | [README.md](README.md) | Human user quick start |
| **Agent Spec + Architecture** | [AGENTS.md](AGENTS.md) | AI coding assistant manual |
| **Coding Guide** | [CLAUDE.md](CLAUDE.md) | Claude context + architecture quick reference |
| **E-SMILES Spec** | [docs/specs/esmiles-spec.md](docs/specs/esmiles-spec.md) | Molecular representation spec |
| **MoleCode Spec** | [docs/specs/molecode-spec.md](docs/specs/molecode-spec.md) | Graph syntax spec |
| **Tech Stack** | [docs/TECH_STACK.md](docs/TECH_STACK.md) | Dependency selection details |
| **Pipeline Redesign** | [docs/pipeline-redesign.md](docs/pipeline-redesign.md) | Parsing pipeline incremental design |
| **Architecture Conventions** | [docs/specs/architecture-conventions.md](docs/specs/architecture-conventions.md) | Module boundaries and layering constraints |

## License

[CC BY-NC-SA 4.0](LICENSE) — Non-commercial use only

## Contact

- **GitHub Issues**: Report bugs or suggest features
- **Email**: Contact MBForge Team

---

**MBForge** — Bringing molecular literature to life.

---
---

# 中文

> **让分子科学文献活起来。** MBForge 是一个桌面端 AI 工作台，将 PDF 文献转化为可检索、可推理的分子知识库，支持自然语言对话查询。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![React 19](https://img.shields.io/badge/React-19-blue.svg)](https://react.dev/)
[![Tauri v2](https://img.shields.io/badge/Tauri-v2-orange.svg)](https://tauri.app/)
[![Rust](https://img.shields.io/badge/Rust-2021_edition-red)](https://www.rust-lang.org/)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](LICENSE)

## 什么是 MBForge？

MBForge（Molecular Knowledge Base）是一个面向**药物发现**和**分子科学**研究者的桌面应用。它解决一个核心痛点：

> **文献中的分子结构和活性数据散落在 PDF 各处，手动整理费时费力，且难以检索和推理。**

### 核心工作流

```
PDF 文档
    ↓ 智能解析
结构化数据（化合物 + 活性数据 + 发现）
    ↓ 分子入库
本地知识库（SQLite + 向量索引）
    ↓ AI 对话
自然语言查询 + 推理分析
```

## 核心特性

### 智能 PDF 解析

- **多引擎可选**：Rust 原生解析（lopdf）/ PyMuPDF / MinerU / LlamaParse / UniParser
- **意图驱动**：只提取你需要的内容（如"提取 TABLE 1 中的活性数据"），跳过无关章节
- **图像分子识别**：YOLO 检测 + MolScribe（Swin Transformer）将化学结构图转为 SMILES
- **结构化输出**：化合物、活性数据、关键发现、不确定项，自动生成 Markdown 报告

### AI Agent 对话

- **本地 ReAct Agent**：20+ 工具，支持知识库检索、分子查询、文件操作
- **上下文增强**：自动检索相关文献和分子数据，提供精准回答
- **多轮记忆**：对话历史持久化，支持复杂推理任务
- **多 LLM 支持**：OpenAI / Anthropic / Ollama（本地模型）

### 分子数据库

- **三层表示架构**：
  - **SMILES**：事实来源，RDKit/chematic 兼容
  - **E-SMILES**：语义扩展，支持 Markush 结构和 R-group 标记
  - **MoleCode**：LLM 友好的 Mermaid 图语法，显式拓扑结构
- **智能去重**：Tanimoto 相似度 + 自动聚类
- **属性估算**：分子量、氢键供体/受体、可旋转键数
- **全量搜索**：FTS5 全文 + 向量语义 + Rerank 重排序

### SAR 分析

- **结构-活性关系**：Scaffold 聚类、活性悬崖检测
- **R-group 分析**：可视化取代基位置与活性关联
- **修正工作流**：OCR 结果人工审核与修正

### 项目管理

- **Vault 模式**：一个文件夹即一个项目，类似 Obsidian
- **统一存储**：molecules.db + vectors.db + semantic_cache.json
- **模型管理**：统一目录，支持下载/查看/删除，含许可证信息
- **审计日志**：所有操作可追溯

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│  React + Vite + TypeScript  (port 5173)                      │
│  ┌──────────┐ ┌──────────────┐ ┌─────────────────────────┐  │
│  │  Chat    │ │  Molecule    │ │  Settings / Project     │  │
│  │  Agent   │ │  Library     │ │  View / SAR Analysis    │  │
│  └────┬─────┘ └──────┬───────┘ └───────────┬─────────────┘  │
│       │              │                     │                │
│  ┌────┴──────────────┴─────────────────────┴─────────────┐  │
│  │              api/tauri/index.ts                        │  │
│  │    (window.__TAURI__.invoke → Rust commands)           │  │
│  └───────────────────────┬───────────────────────────────┘  │
└──────────────────────────┼──────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────┐
│  Tauri Shell (Tauri v2 + Rust Core + Python Sidecar)        │
│  ┌────────────────────┐  ┌──────────────────────────────┐  │
│  │  src-tauri/src/    │  │  FastAPI Sidecar             │  │
│  │                    │  │  (port 18792)                 │  │
│  │  commands/ (18)    │  │  ┌────────────────────────┐  │  │
│  │  core/     (74)    │  │  │ Qwen3-Embedding       │  │  │
│  │    agent/          │  │  │ Qwen3-Reranker        │  │  │
│  │    chem/           │  │  │ MolDet (YOLO)         │  │  │
│  │    document/       │  │  │ MolScribe (Swin+TR)   │  │  │
│  │    molecule/       │  │  └────────────────────────┘  │  │
│  │  parsers/  (27)    │  │                              │  │
│  └────────────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 双语言架构

| 层级 | 语言 | 职责 |
|------|------|------|
| **Rust 核心** | Rust | Agent 循环、PDF 原生解析、SQLite 数据库、Tauri IPC 命令层、API 模型调用 |
| **Python 服务** | Python | 本地模型推理（Embedding、Rerank、MolDet、MolScribe）、FastAPI REST API |
| **前端** | TypeScript | React 组件、页面路由、状态管理、Tauri 桥接 |

### 性能优化

- **Rust 共享 HTTP 客户端**：4 个按超时分类的 LazyLock 单例，避免每次请求新建连接池
- **Python 异步非阻塞**：所有模型推理路由通过 `run_in_executor` 包装
- **启动模型预热**：FastAPI lifespan 在后台线程预加载 Embedding/Rerank/MolDet/MolScribe
- **requests.Session 复用**：UniParser 客户端使用持久连接

## 快速开始

### 一键配置

```bash
# Linux/macOS
./setup/index.sh

# Windows
setup\index.bat
```

交互式脚本会引导你完成：
1. 环境检查与依赖安装
2. UniParser 服务配置
3. Ollama 检测
4. LLM 提供商选择（OpenAI/Anthropic/Ollama）
5. Embedding/Rerank 模型配置
6. ModelScope 模型下载
7. 写入 `.env` 配置文件
8. 验证安装

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

## 技术栈

| 类别 | 技术 | 版本 | 用途 |
|------|------|------|------|
| **Rust 核心** | Tauri v2, lopdf, rusqlite, reqwest, tokio | 2 | 桌面壳、PDF 解析、数据库、HTTP、异步 |
| **Python 服务** | FastAPI, uvicorn, PyTorch (CUDA 12.8) | ≥0.115, ≥2.6 | REST API、模型推理 |
| **前端** | React 19, TypeScript, Vite 6 | 19, 6 | UI 框架、构建工具 |
| **化学信息学** | chematic (Rust), RDKit (Python), MolScribe | — | 分子解析、指纹、图像识别 |
| **AI/ML** | sentence-transformers, ultralytics (YOLO) | ≥2.5, ≥8.3 | Embedding、分子检测 |
| **PDF 解析** | lopdf (Rust), PyMuPDF, MinerU, LlamaParse, UniParser | — | 多引擎文档解析 |
| **包管理** | uv (Python), Cargo (Rust), npm (前端) | — | 依赖管理 |

## 测试

```bash
# Rust 测试
cd src-tauri && cargo test

# Python 测试
uv run pytest tests/ -v

# 代码检查
uv run ruff check src/ && uv run ruff format src/ --check
```

## 已知局限

> 我们相信透明度。以下是目前正在积极解决的已知局限：

### 架构债务

1. **chem_validate.rs / core/chem.rs 重叠**：重复的化学验证逻辑需要合并
2. **vector_store.rs 接口冗余**：多个向量存储实现存在重叠 API
3. **std::sync::Mutex 在异步上下文中使用**：阻塞互斥锁在异步代码路径中可能导致死锁

### 性能瓶颈

1. **27 分钟管线**：LLM 调用是串行的，导致复杂文档处理时间过长
2. **无成本追踪**：没有 LLM API 使用的预算执行或成本监控
3. **Python Sidecar 单进程**：模型服务器无连接池或优雅降级

### 功能缺口

1. **chematic 依赖**：基于 Git 的依赖没有稳定发布标签
2. **tracing 覆盖不全**：跨边界调用的可观测性不完整
3. **constants.rs 生成机制**：代码生成机制部分失效

### UI/UX 问题

1. **移动端支持**：无平板/手机查看的响应式设计
2. **协作功能**：无实时多人协作功能
3. **导出格式**：除 Markdown 外导出选项有限

## 开发路线图

### 2026 Q3 — 稳定性与性能

- [ ] 合并重叠的化学验证模块
- [ ] 实现管线中 LLM 调用并行化（目标：<5 分钟）
- [ ] 添加 BudgetEnforcer 用于成本追踪
- [ ] 修复 vector_store 接口冗余
- [ ] 扩展 tracing 到所有跨边界调用

### 2026 Q4 — 增强 AI 能力

- [ ] 多模态 RAG（文本 + 图像 + 分子结构）
- [ ] Agent 工作流自动化（定时任务、批量处理）
- [ ] 领域特定操作的自定义工具创建 UI
- [ ] 集成外部数据库（ChEMBL、PubChem）

### 2027 — 平台演进

- [ ] 移动端/平板伴侣应用
- [ ] 实时协作（多人知识库）
- [ ] 社区扩展插件系统
- [ ] 端到端加密的云同步
- [ ] 高级 SAR 可视化（3D 分子视图）

## 贡献

欢迎贡献！请参阅 [AGENTS.md](AGENTS.md) 了解开发规范。

### 提交规范

```
<type>(<scope>): <subject>

类型: feat | fix | refactor | perf | test | docs | chore
范围: frontend | rust | python | tauri | api | parser | agent | deps
```

## 文档索引

| 文档 | 位置 | 说明 |
|------|------|------|
| **项目入口** | [README.md](README.md) | 人类用户快速开始 |
| **Agent 规范 + 架构** | [AGENTS.md](AGENTS.md) | AI 编码助手操作手册 |
| **编码指南** | [CLAUDE.md](CLAUDE.md) | Claude 上下文 + 架构速查 |
| **E-SMILES 规范** | [docs/specs/esmiles-spec.md](docs/specs/esmiles-spec.md) | 分子表示规范 |
| **MoleCode 规范** | [docs/specs/molecode-spec.md](docs/specs/molecode-spec.md) | 图语法规范 |
| **技术栈** | [docs/TECH_STACK.md](docs/TECH_STACK.md) | 依赖选型详情 |
| **管线重设计** | [docs/pipeline-redesign.md](docs/pipeline-redesign.md) | 解析管线增量设计 |
| **架构约定** | [docs/specs/architecture-conventions.md](docs/specs/architecture-conventions.md) | 模块边界与分层约束 |

## 许可证

[CC BY-NC-SA 4.0](LICENSE) — 非商用，禁止商业使用

## 联系方式

- **GitHub Issues**：报告问题或建议功能
- **邮箱**：联系 MBForge Team

---

**MBForge** — 让分子科学文献活起来。
