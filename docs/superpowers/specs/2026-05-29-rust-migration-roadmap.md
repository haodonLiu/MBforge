# MBForge Rust 迁移路线图

## Context

MBForge 是 React+Tauri 桌面应用，目标是将骨架完全迁移到 Rust，Python 保留为模型推理 sidecar。当前 Rust 层有 Tauri 进程管理 + pdf-inspector + 7 个 Tauri commands。

**核心约束：**
- Rust 是主骨架（编排+数据处理+HTTP+项目管理）
- Python 是推理 sidecar（FastAPI，仅 embedding/rerank/本地 LLM/RDKit）
- 渐进迁移，每个阶段产出可运行软件
- RDKit 和 PyTorch 不重写，保留 Python 调用

## 架构

```
Frontend (React+Vite)
  │
  ▼
Rust Core (src-tauri/src/)
  ├── commands/        — Tauri commands（pdf-inspector, text_ops, classifier, extractor）
  ├── core/            — 项目管理、配置、对话上下文、记忆、轨迹
  ├── parsers/         — PDF 解析、文本分块、分子提取
  ├── agent/           — ReAct 循环、工具注册表、LLM 客户端
  ├── knowledge/       — 向量存储、知识图谱
  ├── models/          — LLM trait 定义、HTTP 客户端（OpenAI/Anthropic 直连）
  │
  └── 调用 Python FastAPI（sidecar，Rust 启动/管理）
       ├── POST /embed      → sentence-transformers 推理
       ├── POST /rerank     → CrossEncoder 推理
       ├── POST /llm/local  → 本地 LLM 推理
       ├── POST /molecule   → RDKit 分子操作
       └── POST /summarize  → LLM 摘要生成（可选，Rust 也可直调 API）
```

**关键点：**
- OpenAI/Anthropic API → Rust 直接 reqwest 调用，不经过 Python
- 本地模型推理 → Python FastAPI sidecar
- RDKit 操作 → Python FastAPI sidecar
- Pipeline 全链路 Rust（pdf-inspector + text_chunk + extractor）
- Python FastAPI 从现有服务器精简而来，只保留推理端点

## 五阶段迁移

### Phase 1: 基础层 Rust 化

**迁移模块（纯计算，无外部依赖）：**
- `utils/config.py` → Rust config（serde + directories）
- `utils/helpers.py` → Rust helpers（sha2, uuid, text_chunk）
- `utils/constants.py` → Rust constants
- `agent/context.py` → Rust LayeredContext
- `agent/trajectory.py` → Rust TrajectoryTracker
- `agent/memory_manager.py` → Rust MemoryManager
- `agent/tools.py` → Rust ToolRegistry
- `core/project.py` → Rust Project（walkdir + sha2 + serde_json）

**集成方式：** PyO3 绑定，Python `try: from mbforge_core import ...`。

### Phase 2: Agent + LLM 客户端 Rust 化

**迁移模块：**
- `models/llm.py` → Rust LLM client（reqwest，OpenAI/Anthropic 直连）
- `models/base.py` → Rust trait 定义
- `agent/agent.py` → Rust ReAct 循环
- `agent/executor.py` → Rust ToolExecutor
- `core/summarizer.py` → Rust SummaryManager

**关键变化：** OpenAI/Anthropic 调用从 Python SDK 迁移到 Rust reqwest。

### Phase 3: PDF Pipeline Rust 化 + LlamaParse

**迁移模块：**
- `parsers/pdf_parser.py` → Rust PDFPipeline（pdf-inspector）
- `parsers/molecule_extractor.py` → Rust extractor（已有）
- `core/document.py` → Rust DocumentProcessor

**LlamaParse 集成：** 作为可选 PDF 解析后端，Python FastAPI 提供 `/parse_pdf` 端点。

### Phase 4: 知识库 Rust 化 + KnowledgeGraphIndex

**迁移模块：**
- `core/knowledge_base.py` → Rust KnowledgeBase（tantivy + HNSW）
- 新增：KnowledgeGraphIndex（LlamaIndex Python 层）

### Phase 5: Python 推理服务精简

**Python FastAPI 保留的端点：**
- `/embed` — sentence-transformers embedding
- `/rerank` — CrossEncoder reranking
- `/llm/local` — 本地 LLM 推理（transformers）
- `/molecule` — RDKit 分子操作（属性计算、SMILES 验证、标准化）
- `/summarize` — LLM 摘要（可选）

**Python 不再负责：**
- ❌ HTTP 路由编排
- ❌ 项目管理
- ❌ PDF 解析
- ❌ 文本处理
- ❌ Agent 循环
- ❌ 向量存储

## 依赖关系

```
Phase 1 (基础层)
  ↓
Phase 2 (Agent + LLM) ← Phase 1 trait
  ↓
Phase 3 (PDF) ← Phase 2 LLM client
  ↓
Phase 4 (KB) ← Phase 1+2
  ↓
Phase 5 (Python 精简) ← Phase 4 KB 接口稳定后
```

## 验证

- `cargo test` — Rust 单测
- `cargo tauri dev` — Tauri 集成
- `uv run pytest` — Python fallback 测试
- `uv run mbforge dev` — 端到端测试
- 性能基准：Rust vs Python 延迟对比
