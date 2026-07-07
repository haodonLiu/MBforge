# MBForge — Molecular Knowledge Base & AI Workbench

[English](#english) | [中文](#中文)

---

# English

> **Bringing molecular literature to life.** MBForge is an AI workbench that
> transforms PDF papers into searchable, reasoning-capable molecular knowledge
> bases with natural language query support.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![React 19](https://img.shields.io/badge/React-19-blue.svg)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.4+-1C3C3C.svg)](https://langchain-ai.github.io/langgraph/)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](LICENSE)

## What is MBForge?

MBForge (Molecular Knowledge Base) is an application for **drug discovery**
and **molecular science** researchers. It solves a critical pain point:

> **Molecular structures and activity data scattered across PDFs are tedious to
> compile manually and difficult to query or reason about.**

### Core Workflow

```
PDF Documents
    ↓ Intelligent Parsing (6-stage pipeline — Phase 1 added molecule extraction)
Structured Data (Compounds + Activity Data + Findings)
    ↓ Molecule Ingestion
Local Knowledge Base (SQLite + OpenKB + PageIndex)
    ↓ AI Conversation (LangGraph agent)
Natural Language Query + Reasoning Analysis
```

## Key Features

### Smart PDF Parsing

- **6-stage pipeline**: classify → extract_text → extract_molecules → normalize → persist_molecules → chunk/index (Phase 1 added molecule extraction)
- **Pluggable backends**: pdfplumber for text, pypdfium2 for rendering, MinerU / LlamaParse / UniParser for difficult PDFs
- **Image Molecule Recognition**: MolDetv2 (YOLO26n) detection + MolScribe (Swin Transformer) converts chemical structure images to SMILES
- **Structured Output**: compounds, activity data, key findings, uncertainties — auto-generated Markdown reports

### AI Agent Conversation

- **LangGraph Agent**: 5 tools for knowledge base retrieval, molecule queries, document fetch, notes, and settings
- **Multi-session**: persistent session store with history replay
- **SSE Streaming**: token-by-token responses via Server-Sent Events
- **Multi-LLM Support**: OpenAI / Anthropic / Ollama (local) / custom OpenAI-compatible

### Molecule Database

- **SMILES canonicalization**: RDKit-backed
- **Smart deduplication**: Tanimoto similarity + auto-clustering
- **Property estimation**: molecular weight, H-bond donors/acceptors, rotatable bonds
- **Tree-reasoned retrieval**: OpenKB + PageIndex generates a hierarchical index per document; vectorless RRF retrieval + dense rerank via LLM

### Knowledge Base

- **Per-project vault**: one folder = one project, Obsidian-style workflow
- **Unified storage**: SQLite business tables + OpenKB PageIndex collection + semantic cache
- **Model management**: download/view/delete with license info
- **Audit log**: all operations traceable

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  React + Vite + TypeScript  (port 5173)                     │
│  ┌──────────┐ ┌──────────────┐ ┌─────────────────────────┐  │
│  │  Chat    │ │  Molecule    │ │  Settings / Project     │  │
│  │  Agent   │ │  Library     │ │  View / KB / SAR        │  │
│  └────┬─────┘ └──────┬───────┘ └───────────┬────────────┘  │
│       │              │                     │               │
│  ┌────┴──────────────┴─────────────────────┴─────────────┐  │
│  │       api/http/  +  api/sse.ts  (HTTP + SSE)         │  │
│  └───────────────────────┬──────────────────────────────┘  │
└──────────────────────────┼─────────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────┼─────────────────────────────────┐
│  FastAPI Backend  (127.0.0.1:18792)                         │
│  ┌─────────────────────┐  ┌─────────────────────────────┐  │
│  │  routers/  (18)     │  │  agent/  (LangGraph)        │  │
│  │  ───────────────    │  │  graph + 5 tools + sessions │  │
│  │  core/              │  │                             │  │
│  │    database         │  │                             │  │
│  │    knowledge_base   │  │                             │  │
│  │    semantic_cache   │  │                             │  │
│  │    project          │  │                             │  │
│  │  pipeline/          │  │                             │  │
│  │    classify         │  │                             │  │
│  │    extract_text     │  │                             │  │
│  │    segment          │  │                             │  │
│  │    chunk            │  │                             │  │
│  │    index            │  │                             │  │
│  │    runner           │  │                             │  │
│  └─────────────────────┘  └─────────────────────────────┘  │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Local model backends  (lazy-loaded)                   │  │
│  │  MolDetv2 (YOLO26n)     MolScribe (Swin + TR)        │  │
│  │  OpenKB + PageIndex (tree reasoning + dense rerank)  │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### Three-tier Architecture

| Layer | Language | Responsibility |
|---|---|---|
| **Frontend** | TypeScript + React | Components, routing, state, HTTP bridge, SSE client |
| **Backend** | Python (FastAPI) | Pipeline, KB, agent, model orchestration |
| **Storage** | SQLite + OpenKB + filesystem | Business data, PageIndex tree, project files |

### Performance Optimizations

- **HTTP keep-alive**: `httpx.AsyncClient` reused per backend, configured timeouts
- **Python async non-blocking**: model inference wrapped in `run_in_executor`
- **Lazy model loading**: no backend is prewarmed at startup; embed/rerank/moldet/molscribe load on first use to save startup time & VRAM
- **PageIndex hybrid search**: tree reasoning from PageIndex + OpenKB dense rerank for top-k finalization

## Quick Start

### Manual Start

```bash
# Install Python dependencies
uv sync --dev

# Start backend (Terminal 1) — FastAPI on 127.0.0.1:18792
uv run uvicorn mbforge.app:app --host 127.0.0.1 --port 18792

# Start frontend (Terminal 2) — Vite dev server on :5173
cd frontend && npm run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api/*` to the
Python backend, so the frontend uses relative URLs only.

### Production Build

```bash
# Build frontend bundle
cd frontend && npm run build

# Serve frontend/dist behind any static file server
# Run backend behind a reverse proxy (nginx, caddy) with SSE-aware timeouts
```

### Docker (Recommended for Deployment)

Single GPU image with multi-stage build (frontend → python-deps → CUDA runtime).

```bash
# Build (first time 10-20 min; layer cache makes incremental ~30s)
bash scripts/build_docker.sh        # Linux/macOS/Git Bash
scripts\build_docker.bat            # Windows cmd

# Run (GPU)
docker run --rm --gpus all -p 18792:18792 mbforge:dev

# Run with persistent config + model cache
docker run --rm --gpus all \
    -p 18792:18792 \
    -v mbforge-config:/root/.config/MBForge \
    -v mbforge-cache:/root/.cache \
    mbforge:dev

# Verify
curl http://localhost:18792/api/v1/health
# Browser: http://localhost:18792
```

**Requirements**:
- Docker 20.10+ (Docker Desktop on Windows/macOS)
- NVIDIA GPU + [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) for GPU passthrough
- WSL2 backend (Windows Docker Desktop) with ≥8 GB RAM

**What's inside** (`dist/mbforge` layers):
- `nvidia/cuda:12.8.0-runtime-ubuntu22.04` base
- Python 3.12 + uv-managed `.venv` (PyTorch CUDA + Ultralytics + RDKit + OpenKB + PageIndex + LangGraph)
- React frontend `dist/` (mounted as `/` static)

**Caveats**:
- First launch downloads model weights (~500 MB) from ModelScope/HF
- Not bundled: NVIDIA driver / CUDA toolkit (host-side install only)
- No CPU-only image — use the manual start path instead

## Tech Stack

| Category | Technology | Version | Purpose |
|---|---|---|---|
| **Frontend** | React, TypeScript, Vite | 19, 6, 8 | UI framework, type system, build tool |
| **Backend** | FastAPI, uvicorn, Pydantic | ≥0.115, ≥0.30, ≥2.6 | REST + SSE API, validation |
| **Agent** | LangGraph, langchain | ≥0.4, ≥0.3 | Agent graph, LLM provider abstraction |
| **Cheminformatics** | RDKit | — | SMILES canonicalization, fingerprints |
| **AI/ML** | sentence-transformers, ultralytics (YOLO) | ≥2.5, ≥8.3 | Embedding, molecule detection |
| **PDF Parsing** | pdfplumber, pypdfium2 | — | Text + image extraction |
| **Storage** | SQLite (stdlib), OpenKB + PageIndex | — | Business data + tree-reasoned KB |
| **Package Manager** | uv (Python), npm (frontend) | — | Dependency management |

## Testing

```bash
# Python tests
uv run pytest tests/ -v

# Frontend tests
cd frontend && npm run test

# Lint + format
uv run ruff check src/ && uv run ruff format src/ --check
cd frontend && npm run lint
```

## Known Limitations

> We believe in transparency. Here are the current limitations we're actively
> working on. See `TODO/INDEX.md` for the full prioritized list.

### Test Coverage Gap

The Python backend has good code structure but sparse test coverage (only
`tests/unit/parsers/test_coref_alt.py` is currently populated). Most of the 53
routes across 18 routers have no automated test. Priority work in
`TODO/INDEX.md` P1/P2 to bring coverage to the ≥70% target.

### Performance Bottlenecks

1. **Sequential pipeline stages**: a single PDF goes through classify →
   extract_text → extract_molecules → normalize → persist_molecules →
   chunk/index in series; LLM-heavy stages don't yet fan out across pages.
2. **First-call latency**: embed/rerank/moldet/molscribe are lazy-loaded, so
   the first user request that touches them pays 5–30s of model load time.
3. **No cost tracking**: no budget enforcement or cost monitoring for LLM API
   usage.

### Feature Gaps

1. **Mobile support**: no responsive design for tablet/phone viewing.
2. **Collaboration**: no real-time multi-user knowledge base.
3. **Export formats**: limited to Markdown.

## Roadmap

### 2026 Q3 — Stability & Performance

- [ ] Bring Python test coverage to ≥70% (P1 items in `TODO/INDEX.md`)
- [ ] Implement parallel LLM calls in pipeline (target: <5 min for typical paper)
- [ ] Add budget enforcement for LLM API usage
- [ ] Document SSE reconnect logic + first-call latency UX

### 2026 Q4 — Enhanced AI Capabilities

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

Contributions are welcome! See [AGENTS.md](AGENTS.md) for development
guidelines, [TODO/INDEX.md](TODO/INDEX.md) for prioritized work, and
[CLAUDE.md](CLAUDE.md) for repository-level AI context.

### Commit Convention

```
<type>(<scope>): <subject>

Types:  feat | fix | refactor | perf | test | docs | chore
Scopes: frontend | python | api | router | pipeline | agent | backend | deps
```

## Documentation

| Document | Location | Description |
|---|---|---|
| **Project entry** | [README.md](README.md) | Human user quick start |
| **Repository guidelines** | [AGENTS.md](AGENTS.md) | AI coding assistant manual |
| **AI quick-ref** | [CLAUDE.md](CLAUDE.md) | Repository-level AI context |
| **Task board** | [TODO/INDEX.md](TODO/INDEX.md) | Prioritized work (P0–P3) |
| **Architecture conventions** | [docs/specs/architecture-conventions.md](docs/specs/architecture-conventions.md) | Module boundaries and layering |
| **Molecule representation** | [docs/specs/molecular-representation.md](docs/specs/molecular-representation.md) | SMILES / E-SMILES / MoleCode |
| **E-SMILES spec** | [docs/specs/esmiles-spec.md](docs/specs/esmiles-spec.md) | Extended SMILES format |
| **MoleCode spec** | [docs/specs/molecode-spec.md](docs/specs/molecode-spec.md) | Graph syntax |
| **Code style** | [docs/specs/code-style.md](docs/specs/code-style.md) | Python + TS conventions |
| **References** | [docs/REFERENCES.md](docs/REFERENCES.md) | Open-source attribution |

## License

[CC BY-NC-SA 4.0](LICENSE) — Non-commercial use only

## Contact

- **GitHub Issues**: report bugs or suggest features
- **Email**: contact MBForge Team

---

**MBForge** — Bringing molecular literature to life.

---

# 中文

> **让分子科学文献活起来。** MBForge 是一个 AI 工作台，将 PDF 文献转化为可
> 检索、可推理的分子知识库，支持自然语言对话查询。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![React 19](https://img.shields.io/badge/React-19-blue.svg)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.4+-1C3C3C.svg)](https://langchain-ai.github.io/langgraph/)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](LICENSE)

## 什么是 MBForge？

MBForge（Molecular Knowledge Base）是一个面向**药物发现**和**分子科学**
研究者的应用。它解决一个核心痛点：

> **文献中的分子结构和活性数据散落在 PDF 各处，手动整理费时费力，且难
> 以检索和推理。**

### 核心工作流

```
PDF 文档
    ↓ 智能解析（6 阶段管线，Phase 1 新增 extract_molecules）
结构化数据（化合物 + 活性数据 + 发现）
    ↓ 分子入库
本地知识库（SQLite + OpenKB + PageIndex）
    ↓ AI 对话（LangGraph agent）
自然语言查询 + 推理分析
```

## 核心特性

### 智能 PDF 解析

- **6 阶段管线**：classify → extract_text → extract_molecules → normalize → persist_molecules → chunk/index（Phase 1 新增分子抽取）
- **可插拔后端**：pdfplumber 提取文本，pypdfium2 渲染页面，困难 PDF 走
  MinerU / LlamaParse / UniParser
- **图像分子识别**：MolDetv2（YOLO26n）检测 + MolScribe（Swin Transformer）
  将化学结构图转为 SMILES
- **结构化输出**：化合物、活性数据、关键发现、不确定项，自动生成 Markdown
  报告

### AI Agent 对话

- **LangGraph Agent**：5 个工具，覆盖知识库检索、分子查询、文档获取、笔记、
  设置
- **多会话**：持久化会话存储，支持历史回放
- **SSE 流式响应**：逐 token 输出（Server-Sent Events）
- **多 LLM 支持**：OpenAI / Anthropic / Ollama（本地）/ 自定义 OpenAI 兼容

### 分子数据库

- **SMILES 规范化**：RDKit 后端
- **智能去重**：Tanimoto 相似度 + 自动聚类
- **属性估算**：分子量、氢键供体/受体、可旋转键数
- **树推理检索**：OpenKB + PageIndex 为每篇文档生成层次化索引，结合向量检索与 LLM 重排序

### 知识库

- **Vault 模式**：一个文件夹即一个项目，类似 Obsidian
- **统一存储**：SQLite 业务表 + OpenKB PageIndex 集合 + 语义缓存
- **模型管理**：支持下载/查看/删除，含许可证信息
- **审计日志**：所有操作可追溯

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│  React + Vite + TypeScript  (port 5173)                     │
│  ┌──────────┐ ┌──────────────┐ ┌─────────────────────────┐  │
│  │  Chat    │ │  Molecule    │ │  Settings / Project     │  │
│  │  Agent   │ │  Library     │ │  View / KB / SAR        │  │
│  └────┬─────┘ └──────┬───────┘ └───────────┬────────────┘  │
│       │              │                     │               │
│  ┌────┴──────────────┴─────────────────────┴─────────────┐  │
│  │       api/http/  +  api/sse.ts  (HTTP + SSE)         │  │
│  └───────────────────────┬──────────────────────────────┘  │
└──────────────────────────┼─────────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────┼─────────────────────────────────┐
│  FastAPI Backend  (127.0.0.1:18792)                         │
│  ┌─────────────────────┐  ┌─────────────────────────────┐  │
│  │  routers/  (18 个)  │  │  agent/  (LangGraph)        │  │
│  │  ───────────────    │  │  graph + 5 tools + sessions │  │
│  │  core/              │  │                             │  │
│  │    database         │  │                             │  │
│  │    knowledge_base   │  │                             │  │
│  │    semantic_cache   │  │                             │  │
│  │    project          │  │                             │  │
│  │  pipeline/          │  │                             │  │
│  │    classify         │  │                             │  │
│  │    extract_text     │  │                             │  │
│  │    segment          │  │                             │  │
│  │    chunk            │  │                             │  │
│  │    index            │  │                             │  │
│  │    runner           │  │                             │  │
│  └─────────────────────┘  └─────────────────────────────┘  │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  本地模型后端  (懒加载)                                │  │
│  │  MolDetv2 (YOLO26n)     MolScribe (Swin + TR)        │  │
│  │  OpenKB + PageIndex (tree reasoning + dense rerank)  │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 三层架构

| 层级 | 技术 | 职责 |
|---|---|---|
| **前端** | TypeScript + React | 组件、路由、状态、HTTP 桥、SSE 客户端 |
| **后端** | Python (FastAPI) | 管线、知识库、agent、模型编排 |
| **存储** | SQLite + OpenKB + 文件系统 | 业务数据、PageIndex 树、项目文件 |

### 性能优化

- **HTTP keep-alive**：每个后端复用 `httpx.AsyncClient`，按超时分级
- **Python 异步非阻塞**：模型推理通过 `run_in_executor` 包装
- **模型懒加载**：启动时不预热任何后端；embed/rerank/moldet/molscribe 首次调用
  时加载，节省启动时间与显存
- **PageIndex 混合检索**：先 PageIndex 树推理，再 OpenKB 密集检索 + LLM 重排序取 top-k

## 快速开始

### 手动启动

```bash
# 安装 Python 依赖
uv sync --dev

# 启动后端（终端 1）— FastAPI on 127.0.0.1:18792
uv run uvicorn mbforge.app:app --host 127.0.0.1 --port 18792

# 启动前端（终端 2）— Vite dev server on :5173
cd frontend && npm run dev
```

打开 <http://localhost:5173>。Vite 开发服务器将 `/api/*` 代理到 Python 后端，
前端只使用相对路径。

### 生产构建

```bash
# 构建前端
cd frontend && npm run build

# 用任意静态文件服务器部署 frontend/dist/
# 用反向代理（nginx、caddy）部署后端，注意 SSE 超时配置
```

## 技术栈

| 类别 | 技术 | 版本 | 用途 |
|---|---|---|---|
| **前端** | React, TypeScript, Vite | 19, 6, 8 | UI 框架、类型系统、构建工具 |
| **后端** | FastAPI, uvicorn, Pydantic | ≥0.115, ≥0.30, ≥2.6 | REST + SSE API、参数校验 |
| **Agent** | LangGraph, langchain | ≥0.4, ≥0.3 | Agent 图、LLM provider 抽象 |
| **化学信息学** | RDKit | — | SMILES 规范化、指纹 |
| **AI/ML** | sentence-transformers, ultralytics (YOLO) | ≥2.5, ≥8.3 | Embedding、分子检测 |
| **PDF 解析** | pdfplumber, pypdfium2 | — | 文本 + 图像提取 |
| **存储** | SQLite (stdlib), OpenKB + PageIndex | — | 业务数据 + 树推理 KB |
| **包管理** | uv (Python), npm (前端) | — | 依赖管理 |

## 测试

```bash
# Python 测试
uv run pytest tests/ -v

# 前端测试
cd frontend && npm run test

# 代码检查
uv run ruff check src/ && uv run ruff format src/ --check
cd frontend && npm run lint
```

## 已知局限

> 我们相信透明度。以下是目前正在积极解决的已知局限，详见
> [TODO/INDEX.md](TODO/INDEX.md)。

### 测试覆盖缺口

Python 后端结构良好，但测试覆盖稀疏（目前仅有
`tests/unit/parsers/test_coref_alt.py` 一个 unit test）。53 个 routes（分布在
18 个 routers）中大多数没有自动化测试。`TODO/INDEX.md` P1/P2 中的优先级工作
目标是把覆盖率提升到 ≥70%。

### 性能瓶颈

1. **管线阶段串行**：单个 PDF 走 classify → extract_text → extract_molecules
   → normalize → persist_molecules → chunk/index；LLM 密集阶段尚未在页面间并行
2. **首次调用延迟**：embed/rerank/moldet/molscribe 是懒加载，首次触发的
   请求会付 5–30 秒模型加载成本
3. **无成本追踪**：LLM API 使用无预算执行与成本监控

### 功能缺口

1. **移动端支持**：无平板/手机响应式设计
2. **协作功能**：无实时多人知识库
3. **导出格式**：除 Markdown 外选项有限

## 开发路线图

### 2026 Q3 — 稳定性与性能

- [ ] Python 测试覆盖率提升到 ≥70%（`TODO/INDEX.md` P1 项）
- [ ] 管线 LLM 调用并行化（目标：<5 分钟）
- [ ] 添加 LLM API 预算执行
- [ ] 完善 SSE 重连与首次调用延迟 UX

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

欢迎贡献！请参阅 [AGENTS.md](AGENTS.md) 了解开发规范，
[TODO/INDEX.md](TODO/INDEX.md) 了解优先级工作，
[CLAUDE.md](CLAUDE.md) 了解仓库级 AI 上下文。

### 提交规范

```
<type>(<scope>): <subject>

类型: feat | fix | refactor | perf | test | docs | chore
范围: frontend | python | api | router | pipeline | agent | backend | deps
```

## 文档索引

| 文档 | 位置 | 说明 |
|---|---|---|
| **项目入口** | [README.md](README.md) | 人类用户快速开始 |
| **仓库指南** | [AGENTS.md](AGENTS.md) | AI 编码助手操作手册 |
| **AI 速查** | [CLAUDE.md](CLAUDE.md) | 仓库级 AI 上下文 |
| **任务表** | [TODO/INDEX.md](TODO/INDEX.md) | 优先级工作（P0–P3） |
| **架构约定** | [docs/specs/architecture-conventions.md](docs/specs/architecture-conventions.md) | 模块边界与分层约束 |
| **分子表示** | [docs/specs/molecular-representation.md](docs/specs/molecular-representation.md) | SMILES / E-SMILES / MoleCode |
| **E-SMILES 规范** | [docs/specs/esmiles-spec.md](docs/specs/esmiles-spec.md) | 扩展 SMILES 格式 |
| **MoleCode 规范** | [docs/specs/molecode-spec.md](docs/specs/molecode-spec.md) | 图语法 |
| **代码风格** | [docs/specs/code-style.md](docs/specs/code-style.md) | Python + TS 规范 |
| **致谢与引用** | [docs/REFERENCES.md](docs/REFERENCES.md) | 开源项目致谢 |

## 许可证

[CC BY-NC-SA 4.0](LICENSE) — 非商用，禁止商业使用

## 联系方式

- **GitHub Issues**：报告问题或建议功能
- **邮箱**：联系 MBForge Team

---

**MBForge** — 让分子科学文献活起来。