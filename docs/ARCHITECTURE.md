# MBForge Architecture

> 系统架构、核心设计决策、数据流和技术细节。

**Related:** [API Reference](API.md) · [Tech Stack](TECH_STACK.md) · [Development Guide](DEVELOPMENT.md)

---

## 1. Overview

MBForge is a molecular science knowledge base platform with a React+Vite+Tauri frontend and FastAPI backend. Core workflow:

```
PDF → DocumentProcessor → MoleculeExtractor → DocumentSummarizer
       → KnowledgeBase (ChromaDB) + MoleculeDatabase (SQLite + RDKit)
       → AI Agent (ReAct) → User Chat
```

**Design Goals:**
- Vault-based project management (one folder = one project)
- Offline-first with optional cloud services
- Extensible workflow modules (generation, docking, QSAR, MD)
- Multi-model support (OpenAI, Anthropic, local vLLM/Ollama)

---

## 2. System Architecture

```
┌─────────────────────┐     ┌─────────────────────────┐
│  React+Vite Frontend │────▶│  FastAPI Model Server    │
│  (port 5173)         │     │  (port 18792)            │
│  Tauri Bridge        │     │  /api/v1/*               │
└─────────────────────┘     └─────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
             ┌──────────┐    ┌──────────┐    ┌──────────┐
             │ PDFParser │    │ Agent    │    │ Knowledge│
             │ Pipeline  │    │ (ReAct)  │    │ Base     │
             └──────────┘    └──────────┘    └──────────┘
```

**Layers:**
1. **Frontend** — React 19 + Vite 6 + TypeScript, served by Vite dev server or Tauri
2. **Model Server** — FastAPI + uvicorn, 12 API routers
3. **Agent Layer** — ReAct loop with 10 tools, layered context, memory
4. **Model Abstraction** — BaseLLM/BaseEmbedder/BaseReranker/BaseVLM
5. **Core Data** — Project, KnowledgeBase, MoleculeDatabase, Summarizer
6. **Parser Pipeline** — PDFParserPipeline, MoleculeExtractor, DocumentProcessor
7. **Storage** — ChromaDB (vectors), SQLite (molecules), local filesystem

---

## 3. Module Layout

### 3.1 `core/` — Data Models

| File | Class | Responsibility |
|------|-------|----------------|
| `project.py` | `Project`, `DocumentEntry` | Vault management, file index, `.mbforge/` metadata |
| `knowledge_base.py` | `KnowledgeBase` | ChromaDB wrapper: `index_document`, `search`, `hybrid_search` |
| `mol_database.py` | `MoleculeDatabase`, `MoleculeRecord` | SQLite + FTS5, RDKit property computation |
| `document.py` | `DocumentProcessor`, `ExtractedContent` | PDF/text/markdown extraction |
| `summarizer.py` | `DocumentSummarizer`, `SummaryManager` | L0/L1/L2 layered summarization |
| `settings.py` | `ProjectSettings` | Project-level config |
| `memory.py` | `AgentMemory` | Agent 6-type memory templates |
| `todo_manager.py` | `TodoManager` | Todo list persistence |

### 3.2 `models/` — AI Model Abstraction

| File | Class | Backend |
|------|-------|---------|
| `base.py` | `BaseLLM`, `BaseEmbedder`, `BaseReranker`, `BaseVLM` | Abstract interfaces |
| `llm.py` | `OpenAILLM` | OpenAI-compatible API |
| `anthropic_llm.py` | `AnthropicLLM` | Anthropic Claude |
| `embedding.py` | `SentenceTransformerEmbedder`, `Qwen3Embedder`, `APIEmbedder` | Local + API |
| `rerank.py` | `SentenceTransformerReranker` | Local |
| `vlm.py` | `APIVLM` | API |
| `client.py` | `LLMClient`, `ModelClientFactory` | HTTP clients for model server |

### 3.3 `model_server/` — FastAPI Backend

| Router | Prefix | Function |
|--------|--------|----------|
| `llm` | `/api/v1/llm` | LLM chat/stream |
| `embed` | `/api/v1/embed` | Text embedding |
| `rerank` | `/api/v1/rerank` | Result reranking |
| `vlm` | `/api/v1/vlm` | Vision language model |
| `agent` | `/api/v1/agent` | Agent chat/stream |
| `kb` | `/api/v1/kb` | Knowledge base search |
| `molecule` | `/api/v1/molecule` | Molecule database |
| `project` | `/api/v1/project` | Project management |
| `file` | `/api/v1/file` | File upload/delete |
| `health` | `/api/v1/health` | Health check |
| `settings` | `/api/v1/settings` | App settings |
| `moldet` | `/api/v1/moldet` | Molecule detection |
| `uniparser` | `/api/v1/uniparser` | PDF parsing |

### 3.4 `parsers/` — PDF Parsing & Molecule Extraction

| File | Class | Role |
|------|-------|------|
| `pdf_parser.py` | `PDFParserPipeline` | Orchestrates full parsing pipeline |
| `molecule_extractor.py` | `MoleculeExtractor` | Regex + LLM SMILES extraction |
| `file_processor.py` | `FileProcessor` | Multi-format file handling |
| `molecule/mol_image_pipeline.py` | `MolImagePipeline` | YOLO detection + MolScribe recognition |
| `uniparser/` | `ParserClient` | UniParser API wrapper |

### 3.5 `agent/` — ReAct Agent

| File | Class | Role |
|------|-------|------|
| `agent.py` | `ProjectAgent` | ReAct loop coordinator |
| `context.py` | `LayeredContext` | Multi-layer context management |
| `executor.py` | `ToolExecutor` | Tool dispatch and execution |
| `tools.py` | `@tool` definitions | 10 agent tools |
| `memory_manager.py` | `MemoryManager` | 6-type memory extraction |
| `trajectory.py` | `TrajectoryTracker` | Tool call logging |

### 3.6 `frontend/` — React Frontend

| Directory | Content |
|-----------|---------|
| `src/components/` | UI components (Chat, ProjectView, Search, Settings, etc.) |
| `src/api/` | API client wrappers |
| `src/hooks/` | Custom React hooks |
| `src/types/` | TypeScript type definitions |
| `src/styles/` | CSS variables and component styles |

---

## 4. Data Flow

### 4.1 PDF Indexing Pipeline

```
User selects PDF
  → DocumentProcessor.extract_text() / extract_images()
  → MoleculeExtractor.extract_from_text() + extract_from_images()
  → DocumentSummarizer.generate_summary() (L0/L1/L2)
  → KnowledgeBase.index_document() (ChromaDB)
  → MoleculeDatabase.add_molecule() (SQLite + RDKit)
```

### 4.2 Agent Chat Flow

```
User sends message
  → ProjectAgent.chat()
    → LayeredContext.build_messages() (system + memory + conversation)
    → LLM.chat() or LLM.call_with_tools()
    → If tool_call: ToolExecutor.execute()
    → Response to user
```

---

## 5. Configuration

Two-tier configuration:

- **Global** (`~/.config/MBForge/config.json`): LLM, embedding, rerank, VLM settings
- **Project** (`.mbforge/settings.json`): Model overrides, workflow toggles

Environment variable overrides: `MBFORGE_LLM_*`, `MBFORGE_EMBED_*`, etc.

---

## 6. Error Handling

Centralized exception hierarchy:

```
MBForgeError (base, status_code + error_code)
  ├── ProjectNotFoundError (404)
  ├── ProjectNotValidError (400)
  ├── ModelNotAvailableError (503)
  ├── APIKeyMissingError (401)
  ├── ConfigError (400)
  ├── ValidationError (422)
  ├── FileAccessError (400)
  └── PathTraversalError (403)
```

Global exception handler in `main.py` converts to structured JSON responses.

---

## 7. Storage Structure

```
.mbforge/
├── index.json          # Document index
├── settings.json       # Project settings
├── kb/                 # ChromaDB vector store
├── molecules.db        # SQLite molecule database
├── summaries/          # LLM-generated summaries
├── extractions/        # Molecule extraction cache
└── trajectories/       # Agent tool call logs
```
