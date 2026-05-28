# MBForge Rust 迁移路线图

## Context

MBForge 是 React+Tauri 桌面应用，目标是将骨架迁移到 Rust，Python 保留为推理 sidecar + LlamaIndex 编排层。

## 架构

```
Frontend (React+Vite)
  │
  ▼
Rust Core (src-tauri/src/) — 主骨架
  ├── PDF 解析（pdf-inspector）
  ├── 文本分块、分子提取、分类
  ├── 项目管理、配置、对话上下文
  ├── LLM API 直连（reqwest → OpenAI/Anthropic）
  ├── 向量存储（tantivy + HNSW）
  └── 调用 Python sidecar（HTTP）
       │
       ▼
Python FastAPI Sidecar — 推理 + LlamaIndex 编排
  ├── LlamaIndex Workflows（Agent 编排、RAG pipeline）
  ├── LlamaIndex KnowledgeGraphIndex
  ├── POST /embed       → sentence-transformers
  ├── POST /rerank      → CrossEncoder
  ├── POST /llm/local   → transformers
  ├── POST /molecule    → RDKit
  └── POST /summarize   → LLM 摘要
```

## 五阶段

### Phase 1: 基础层 Rust 化
- utils (config, helpers, constants)
- agent 数据结构 (context, trajectory, memory, tools)
- core/project.py

### Phase 2: Agent + LLM 客户端 Rust 化
- models/llm.py → Rust reqwest (OpenAI/Anthropic 直连)
- agent/agent.py → Rust ReAct 循环
- agent/executor.py → Rust ToolExecutor

### Phase 3: PDF Pipeline Rust 化 + LlamaParse
- parsers/ → Rust (pdf-inspector + text_ops + extractor)
- LlamaParse 作为可选后端（Python sidecar 提供）

### Phase 4: 知识库 Rust 化 + KnowledgeGraphIndex
- knowledge_base.py → Rust (tantivy + HNSW)
- KnowledgeGraphIndex（LlamaIndex Python 层）

### Phase 5: Python Sidecar 精简
- 精简现有 FastAPI 为纯推理服务
- LlamaIndex Workflows 编排 Agent
- 保留: embedding, rerank, RDKit, 本地 LLM
- 移除: HTTP 路由编排, 项目管理, PDF 解析, 向量存储

## 验证
- `cargo test` — Rust 单测
- `cargo tauri dev` — Tauri 集成
- `uv run pytest` — Python fallback
- 性能基准：Rust vs Python 延迟
