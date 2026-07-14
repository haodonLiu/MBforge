# MBForge — Molecular Knowledge Base & AI Workbench

[English](#english) | [中文](#中文)

---

# English

> **Bringing molecular literature to life.** MBForge turns PDF papers into a
> searchable, reasoning-capable molecular knowledge base with natural-language
> query.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![React 19](https://img.shields.io/badge/React-19-blue.svg)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.4+-1C3C3C.svg)](https://langchain-ai.github.io/langgraph/)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](LICENSE)

## What is MBForge?

Desktop AI workbench for **drug discovery** and **molecular science**. Pain point:

> Molecular structures and activity data scattered across PDFs are slow to
> compile by hand and hard to query or reason over.

### Core workflow

```
PDF
  → 7-stage pipeline (extract → density → markdown → reorganize → activity → index → persist)
  → Local knowledge base (SQLite + OpenKB / PageIndex)
  → LangGraph agent chat + molecule ops
```

## Key features

**Smart PDF parsing**

- **7 modular stages**: Extract → Density → Markdown (MolDetv2-FT + MolScribe + MoleCode) → Reorganize → Activity → Index → Persist
- **Text / render**: pdfplumber + pypdfium2 / PyMuPDF
- **OCR fallback chain**: MinerU → PaddleOCR → GLMOCR → RapidOCR
- **Image → SMILES**: MolDetv2-FT (YOLO26n, joint molecule + coref labels) + MolScribe
- **Activity extraction**: IC50 / Ki / EC50 / Kd from tables

**AI agent**

- LangGraph agent with tools (KB search, molecule search, document fetch, properties, doc list)
- Multi-session store + SSE token streaming
- LLM providers: OpenAI / Anthropic / Ollama / OpenAI-compatible

**Molecule library & KB**

- RDKit canonical SMILES, Tanimoto dedup / clustering, basic property estimates
- Per-library vault (`library_root`, default `~/MBForge`)
- Unified SQLite (`.mbforge/library.db`) + OpenKB PageIndex tree + dense rerank
- Evidence-linked crops under `storage/{doc_id}/`

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  React 19 + Vite 8 + TypeScript  (:5173)             │
│  Chat · Molecule library · Workspace · SAR · Settings│
│  api/http + React Query · SSE                        │
└───────────────────────┬──────────────────────────────┘
                        │ HTTP / SSE
┌───────────────────────┼──────────────────────────────┐
│  FastAPI  (127.0.0.1:18792)                           │
│  routers/  ·  pipeline/ (7 stages)  ·  agent/        │
│  core/ (library, database, artifact)  ·  openkb/     │
│  backends/ moldet_v2_ft · molscribe · ocr chain      │
└──────────────────────────────────────────────────────┘
                        │
          SQLite + OpenKB + filesystem (per library)
```

| Layer | Stack | Role |
|---|---|---|
| Frontend | React 19, TS 6, Vite 8 | UI, React Query server state, SSE |
| Backend | Python 3.12, FastAPI | Pipeline, KB, agent, model I/O |
| Storage | SQLite + OpenKB + files | Business data, tree index, artifacts |

Lazy-loaded local models (first hit ~5–30 s). Blocking inference runs via
`run_in_executor`. Business config lives in `~/MBForge/settings.json`;
`MBFORGE_*` env vars are infrastructure only (host, log level, force-CPU).

## Quick start

**Requirements**: Python 3.12, [uv](https://github.com/astral-sh/uv), Node ≥20.19
(or ≥22.12), npm. GPU optional (needed for MolDet / MolScribe).

```bash
# Install
uv sync --dev
npm --prefix frontend install

# Terminal 1 — backend
uv run uvicorn mbforge.app:app --host 127.0.0.1 --port 18792
# or: python -m mbforge --dev

# Terminal 2 — frontend (proxies /api → 18792)
cd frontend && npm run dev
# one-shot: cd frontend && npm run dev:all
```

Open <http://localhost:5173>. Production: `cd frontend && npm run build` then
serve `frontend/dist/` with the backend (FastAPI mounts it when present).

### Docker (GPU deploy)

```bash
bash scripts/build_docker.sh          # or scripts\build_docker.bat
docker run --rm --gpus all -p 18792:18792 mbforge:dev

# Persist home dir (settings + default library under ~/MBForge)
docker run --rm --gpus all -p 18792:18792 \
  -v mbforge-home:/root/MBForge \
  -v mbforge-cache:/root/.cache \
  mbforge:dev

curl http://localhost:18792/api/v1/health   # Browser: http://localhost:18792
```

Needs Docker 20.10+, NVIDIA GPU + nvidia-container-toolkit (WSL2 on Windows,
≥8 GB RAM). First run downloads model weights (~500 MB). No CPU-only image —
use the manual path for CPU.

## Tech stack

| Area | Choice |
|---|---|
| Frontend | React 19, TypeScript 6, Vite 8, React Query |
| Backend | FastAPI, uvicorn, Pydantic 2, LangGraph |
| Chem / ML | RDKit, Ultralytics (YOLO), MolScribe, RapidOCR / cloud OCR |
| PDF | pdfplumber, pypdfium2, PyMuPDF |
| Storage | SQLite, OpenKB + PageIndex |
| Tooling | **uv** (Python), **npm** (frontend), ruff, vitest |

## Testing

```bash
uv run pytest tests/ -v
uv run pytest tests/ -v -k "<substring>"
cd frontend && npm run test
uv run ruff check src/ && uv run ruff format src/ --check
cd frontend && npm run lint && npx tsc --noEmit
```

## Known limitations

Tracked in [TODO/INDEX.md](TODO/INDEX.md). Snapshot:

- **Coverage still below target** on some critical paths (goal ≥70% core logic)
- **Pipeline mostly serial** per PDF; LLM stages not fully page-parallel
- **First model load** can cost 5–30 s without UX warm-up signal
- **No LLM cost budget** enforcement
- Mobile / multi-user collab / rich export formats are out of scope for now

## Roadmap (high level)

- **Near term**: coverage + data quality, stage error surfacing, confidence UX
- **Next**: parallel LLM stages, multi-modal RAG, external DB links (ChEMBL / PubChem)
- **Later**: collaboration, plugins, mobile companion

Details and priorities: [TODO/INDEX.md](TODO/INDEX.md), [TODO/PHASE0-ROADMAP.md](TODO/PHASE0-ROADMAP.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Prioritized work: [TODO/INDEX.md](TODO/INDEX.md).
Governance: [docs/PROJECT_MANAGEMENT.md](docs/PROJECT_MANAGEMENT.md),
[docs/VERSION_CONTROL.md](docs/VERSION_CONTROL.md). AI assistants: [AGENTS.md](AGENTS.md),
[CLAUDE.md](CLAUDE.md).

```
<type>(<scope>): <subject>
types:  feat | fix | refactor | perf | test | docs | chore
scopes: frontend | python | api | router | pipeline | agent | backend | deps
```

One logical theme per commit (not one commit per file).

## Documentation

Full map: [docs/README.md](docs/README.md) (living vs historical).

| Doc | Purpose |
|---|---|
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev / test / PR workflow |
| [AGENTS.md](AGENTS.md) | AI contributor rules |
| [CLAUDE.md](CLAUDE.md) | AI architecture + commands |
| [TODO/INDEX.md](TODO/INDEX.md) | P0–P3 task board |
| [docs/specs/](docs/specs/) | Architecture, style, MoleCode / E-SMILES |
| [docs/architecture/pipeline-stages.md](docs/architecture/pipeline-stages.md) | 7-stage pipeline |
| [docs/VERSION_CONTROL.md](docs/VERSION_CONTROL.md) | Branches, SemVer, releases |
| [CHANGELOG.md](CHANGELOG.md) | User-visible changes |
| [docs/REFERENCES.md](docs/REFERENCES.md) | Open-source attribution |

## License

[CC BY-NC-SA 4.0](LICENSE) — non-commercial use only.

## Contact

- GitHub Issues for bugs and feature requests
- Email: MBForge Team

**MBForge** — Bringing molecular literature to life.

---

# 中文

> **让分子科学文献活起来。** MBForge 将 PDF 文献变成可检索、可推理的分子知识库，
> 并支持自然语言对话查询。

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![React 19](https://img.shields.io/badge/React-19-blue.svg)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.4+-1C3C3C.svg)](https://langchain-ai.github.io/langgraph/)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](LICENSE)

## 什么是 MBForge？

面向**药物发现**与**分子科学**研究者的桌面 AI 工作台。核心痛点：

> 文献中的分子结构与活性数据散落在 PDF 各处，手工整理费时，且难以检索与推理。

### 核心工作流

```
PDF
  → 7 阶段管线（extract → density → markdown → reorganize → activity → index → persist）
  → 本地知识库（SQLite + OpenKB / PageIndex）
  → LangGraph agent 对话 + 分子操作
```

## 核心特性

**智能 PDF 解析**

- **7 个模块化阶段**：Extract → Density → Markdown（MolDetv2-FT + MolScribe + MoleCode）→ Reorganize → Activity → Index → Persist
- **文本 / 渲染**：pdfplumber + pypdfium2 / PyMuPDF
- **OCR 降级链**：MinerU → PaddleOCR → GLMOCR → RapidOCR
- **图像 → SMILES**：MolDetv2-FT（YOLO26n，分子 + 共指标签联合检测）+ MolScribe
- **活性抽取**：表格中的 IC50 / Ki / EC50 / Kd

**AI Agent**

- LangGraph + 工具（KB 检索、分子检索、文档获取、属性计算、文档列表）
- 多会话 + SSE 流式输出
- LLM：OpenAI / Anthropic / Ollama / OpenAI 兼容接口

**分子库与知识库**

- RDKit 规范 SMILES、Tanimoto 去重 / 聚类、基础物化性质
- 按库隔离（`library_root`，默认 `~/MBForge`）
- 统一 SQLite（`.mbforge/library.db`）+ OpenKB PageIndex 树 + 密集重排
- 证据关联 crop：`storage/{doc_id}/`

## 架构

```
┌──────────────────────────────────────────────────────┐
│  React 19 + Vite 8 + TypeScript  (:5173)             │
│  对话 · 分子库 · 工作区 · SAR · 设置                   │
│  api/http + React Query · SSE                        │
└───────────────────────┬──────────────────────────────┘
                        │ HTTP / SSE
┌───────────────────────┼──────────────────────────────┐
│  FastAPI  (127.0.0.1:18792)                           │
│  routers/  ·  pipeline/（7 阶段） ·  agent/           │
│  core/（library、database、artifact） ·  openkb/      │
│  backends/ moldet_v2_ft · molscribe · ocr 链          │
└──────────────────────────────────────────────────────┘
                        │
          每库 SQLite + OpenKB + 文件系统
```

| 层级 | 技术 | 职责 |
|---|---|---|
| 前端 | React 19, TS 6, Vite 8 | UI、React Query、SSE |
| 后端 | Python 3.12, FastAPI | 管线、KB、agent、模型 I/O |
| 存储 | SQLite + OpenKB + 文件 | 业务数据、树索引、产物 |

本地模型懒加载（首次约 5–30 s）。阻塞推理走 `run_in_executor`。业务配置写在
`~/MBForge/settings.json`；`MBFORGE_*` 仅作基础设施（host、日志级别、force-CPU）。

## 快速开始

**环境**：Python 3.12、[uv](https://github.com/astral-sh/uv)、Node ≥20.19
（或 ≥22.12）、npm。GPU 可选（MolDet / MolScribe 需要）。

```bash
# 安装
uv sync --dev
npm --prefix frontend install

# 终端 1 — 后端
uv run uvicorn mbforge.app:app --host 127.0.0.1 --port 18792
# 或：python -m mbforge --dev

# 终端 2 — 前端（/api 代理到 18792）
cd frontend && npm run dev
# 一键：cd frontend && npm run dev:all
```

打开 <http://localhost:5173>。生产：`cd frontend && npm run build`，后端在
存在 `frontend/dist/` 时自动挂载静态资源。

### Docker（GPU 部署）

```bash
bash scripts/build_docker.sh          # 或 scripts\build_docker.bat
docker run --rm --gpus all -p 18792:18792 mbforge:dev

# 持久化家目录（settings + 默认库 ~/MBForge）
docker run --rm --gpus all -p 18792:18792 \
  -v mbforge-home:/root/MBForge \
  -v mbforge-cache:/root/.cache \
  mbforge:dev

curl http://localhost:18792/api/v1/health   # 浏览器：http://localhost:18792
```

需要 Docker 20.10+、NVIDIA GPU + nvidia-container-toolkit（Windows 用 WSL2，
建议 ≥8 GB RAM）。首次会拉取模型权重（约 500 MB）。无 CPU-only 镜像，CPU 请用手动启动。

## 技术栈

| 类别 | 选型 |
|---|---|
| 前端 | React 19, TypeScript 6, Vite 8, React Query |
| 后端 | FastAPI, uvicorn, Pydantic 2, LangGraph |
| 化学 / ML | RDKit, Ultralytics (YOLO), MolScribe, RapidOCR / 云 OCR |
| PDF | pdfplumber, pypdfium2, PyMuPDF |
| 存储 | SQLite, OpenKB + PageIndex |
| 工具 | **uv**（Python）、**npm**（前端）、ruff、vitest |

## 测试

```bash
uv run pytest tests/ -v
uv run pytest tests/ -v -k "<substring>"
cd frontend && npm run test
uv run ruff check src/ && uv run ruff format src/ --check
cd frontend && npm run lint && npx tsc --noEmit
```

## 已知局限

详见 [TODO/INDEX.md](TODO/INDEX.md)。摘要：

- **覆盖率**在部分关键路径仍低于目标（核心逻辑目标 ≥70%）
- **管线以串行为主**；LLM 阶段尚未充分按页并行
- **首次模型加载**可能 5–30 s，缺少预热 UX
- **无 LLM 成本预算**约束
- 移动端 / 多人协作 / 丰富导出暂不在当前范围

## 路线图（概要）

- **近期**：测试与数据质量、阶段错误透出、置信度 UX
- **下一步**：LLM 阶段并行、多模态 RAG、外部库对接（ChEMBL / PubChem）
- **更远**：协作、插件、移动伴侣

细节与优先级：[TODO/INDEX.md](TODO/INDEX.md)、[TODO/PHASE0-ROADMAP.md](TODO/PHASE0-ROADMAP.md)。

## 贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。任务板：[TODO/INDEX.md](TODO/INDEX.md)。
治理：[docs/PROJECT_MANAGEMENT.md](docs/PROJECT_MANAGEMENT.md)、
[docs/VERSION_CONTROL.md](docs/VERSION_CONTROL.md)。AI 助手：[AGENTS.md](AGENTS.md)、
[CLAUDE.md](CLAUDE.md)。

```
<type>(<scope>): <subject>
类型: feat | fix | refactor | perf | test | docs | chore
范围: frontend | python | api | router | pipeline | agent | backend | deps
```

一主题一 commit（不要按文件拆）。

## 文档索引

完整地图：[docs/README.md](docs/README.md)（活文档 vs 历史快照）。

| 文档 | 用途 |
|---|---|
| [CONTRIBUTING.md](CONTRIBUTING.md) | 开发 / 测试 / PR |
| [AGENTS.md](AGENTS.md) | AI 编码规则 |
| [CLAUDE.md](CLAUDE.md) | AI 架构 + 命令 |
| [TODO/INDEX.md](TODO/INDEX.md) | P0–P3 任务板 |
| [docs/specs/](docs/specs/) | 架构、风格、MoleCode / E-SMILES |
| [docs/architecture/pipeline-stages.md](docs/architecture/pipeline-stages.md) | 7 阶段管线 |
| [docs/VERSION_CONTROL.md](docs/VERSION_CONTROL.md) | 分支、SemVer、发布 |
| [CHANGELOG.md](CHANGELOG.md) | 用户可见变更 |
| [docs/REFERENCES.md](docs/REFERENCES.md) | 开源致谢 |

## 许可证

[CC BY-NC-SA 4.0](LICENSE) — 仅限非商业使用。

## 联系方式

- GitHub Issues：缺陷与功能建议
- 邮箱：MBForge Team

**MBForge** — 让分子科学文献活起来。
