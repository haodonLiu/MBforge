# MBForge Architecture

> 本文档详细描述 MBForge 的系统架构、核心设计决策、数据流和技术细节。

**Related Documentation:** [API Reference](API.md) · [Development Guide](DEVELOPMENT.md) · [Tech Stack](TECH_STACK.md) · [References](../REFERENCES.md)

---

## 1. Overview

MBForge is a PyQt6 desktop application for molecular science and drug discovery research. Its core workflow:

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
┌─────────────────────────────────────────────────────────────┐
│                        UI Layer (PyQt6)                      │
│  MainWindow │ ChatWidget │ PDFViewer │ MolPanel │ FileTree  │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                      Agent Layer (ReAct)                     │
│  ProjectAgent │ LayeredContext │ ToolExecutor │ MemoryManager │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                     Model Abstraction Layer                  │
│  BaseLLM │ BaseEmbedder │ BaseReranker │ BaseVLM            │
│  (OpenAI / Anthropic / SentenceTransformer / API)           │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                      Core Data Layer                         │
│  Project │ KnowledgeBase │ MoleculeDatabase │ Summarizer     │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                     Parser / Pipeline                        │
│  PDFParserPipeline │ MoleculeExtractor │ DocumentProcessor   │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                  Storage / External Services                 │
│  ChromaDB (vectors) │ SQLite (molecules) │ UniParser API     │
│  Local filesystem (.mbforge/)                                │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Module Layout

### 3.1 `core/` — Data Models

| File | Class/Module | Responsibility |
|------|-------------|----------------|
| `project.py` | `Project`, `DocumentEntry` | Vault management, file index, `.mbforge/` metadata |
| `knowledge_base.py` | `KnowledgeBase` | ChromaDB wrapper: `index_document`, `search`, `hybrid_search` |
| `mol_database.py` | `MoleculeDatabase`, `MoleculeRecord` | SQLite + FTS5, RDKit property computation |
| `document.py` | `DocumentProcessor`, `ExtractedContent` | PDF/text/markdown extraction, image extraction |
| `summarizer.py` | `DocumentSummarizer`, `SummaryManager` | L0/L1/L2 layered summarization |
| `settings.py` | `ProjectSettings` | Project-level config (model overrides, workflow toggles) |
| `memory.py` | `AgentMemory` | Agent 6-type memory templates |
| `todo_manager.py` | `TodoManager` | Todo list persistence |

### 3.2 `models/` — AI Model Abstraction

| File | Class | Responsibility |
|------|--------|----------------|
| `base.py` | `BaseLLM`, `BaseEmbedder`, `BaseReranker`, `BaseVLM`, `Message`, `StreamChunk` | Abstract interfaces |
| `llm.py` | `OpenAILLM`, `create_llm_from_config()` | OpenAI-compatible API LLM |
| `anthropic_llm.py` | `AnthropicLLM` | Anthropic Claude series |
| `embedding.py` | `SentenceTransformerEmbedder`, `APIEmbedder` | Local / API embedding |
| `rerank.py` | `SentenceTransformerReranker`, `APIReranker` | Local / API reranking |
| `vlm.py` | `APIVLM` | Vision-language model for PDF image analysis |

### 3.3 `parsers/` — PDF Parsing & Molecule Extraction

| File | Class | Responsibility |
|------|--------|----------------|
| `pdf_parser.py` | `PDFParserPipeline` | Orchestrates full parsing pipeline |
| `molecule_extractor.py` | `MoleculeExtractor` | Regex + LLM-based SMILES extraction |
| `file_processor.py` | `FileProcessor` | Generic file → `ExtractedContent` |

### 3.4 `agent/` — ReAct Agent

| File | Class | Responsibility |
|------|--------|----------------|
| `agent.py` | `ProjectAgent` | ReAct loop coordinator |
| `context.py` | `LayeredContext` | System → Project → Memory → History layers |
| `executor.py` | `ToolExecutor`, `ToolRegistry` | Tool registration and execution |
| `tools.py` | Tool definitions (10 tools) | `search_knowledge`, `search_molecules`, `get_document`, etc. |
| `memory_manager.py` | `MemoryManager` | 6-type memory: user profile, agent experience, project summary, etc. |
| `trajectory.py` | `TrajectoryTracker` | Tool call logging |
| `archive_agent.py` | `ArchiveAgent` | Document/archive search agent |

### 3.5 `ui/` — PyQt6 Interface

| File | Class | Responsibility |
|------|--------|----------------|
| `main_window.py` | `MainWindow` | Main window, assembles all components |
| `chat_widget.py` | `ChatWidget` | Chat interface with streaming |
| `pdf_viewer.py` | `PDFViewer` | PDF rendering via PyMuPDF |
| `mol_panel.py` | `MolPanel` | Molecule list/detail panel |
| `mol_renderer.py` | `MolRenderer` | RDKit → QPixmap molecule image rendering |
| `file_tree.py` | `FileTree` | Project file tree (sidebar) |
| `editor.py` | `MarkdownEditor` | Markdown editing |
| `preview.py` | `MarkdownPreview` | HTML/Markdown preview via QWebEngineView |
| `dialogs.py` | Settings dialogs, About dialog | Configuration UI |

### 3.6 `parser_io/` — UniParser Integration

| File | Class | Responsibility |
|------|--------|----------------|
| `client.py` | `ParserClient` | UniParser API wrapper |
| `config.py` | `ParserConfig`, `load_config()` | Parser-specific config |
| `models.py` | `ParseResult` | Data models |

### 3.7 `workflow/` — Workflow Extensions (Stubs)

`generation.py`, `docking.py`, `qsar.py`, `md.py` — each imports `WorkflowBase` and provides toggle switches. Not yet implemented.

---

## 4. Data Flow

### 4.1 PDF Indexing Pipeline

```
User triggers "Index"
        │
        ▼
Project.scan_files()  ──returns──►  List[DocumentEntry]
        │
        ▼ (for each PDF)
PDFParserPipeline.parse(pdf_path)
        │
        ├─► DocumentProcessor.process()  ──► ExtractedContent
        │       │
        │       ├─► PyMuPDF extract text
        │       ├─► PyMuPDF extract images
        │       └─► split_text_chunks()
        │
        ├─► (optional) VLM.describe_pdf_page() for each image
        │
        ├─► (optional) DocumentSummarizer.summarize()
        │       │        │
        │       │        └─► LLM.chat() → L0/L1/L2 summaries
        │       │                  │
        │       └─► SummaryManager.save()
        │
        ├─► (optional) MoleculeExtractor.extract_from_text()
        │       │        │
        │       │        ├─► Regex for SMILES patterns
        │       │        ├─► LLM for chemical name → SMILES
        │       │        └─► MoleculeRecord list
        │       │                  │
        │       └─► MoleculeDatabase.add_molecule()
        │
        └─► (optional) KnowledgeBase.index_document()
                    │
                    ├─► embed() → chunk vectors
                    └─► ChromaDB collection.add()
```

### 4.2 Agent Chat Pipeline

```
User types query
        │
        ▼
ProjectAgent.chat()
        │
        ├─► LayeredContext.build_messages()
        │       │        │
        │       │        ├─► system_prompt (with tool descriptions)
        │       │        ├─► project context
        │       │        ├─► injected memories
        │       │        └─► conversation history
        │
        ├─► LLM.chat_completion(tools=...)
        │       │
        │       └─► Response { content?, tool_calls? }
        │
        ├─► if tool_calls:
        │       │
        │       └─► ToolExecutor.registry.call(tool_name, args)
        │               │
        │               ├─► search_knowledge → KnowledgeBase.search()
        │               ├─► search_molecules → MoleculeDatabase.search_by_*
        │               ├─► get_document → DocumentProcessor
        │               └─► ...
        │
        └─► return final answer
```

---

## 5. Vault / Project Structure

Each project is a folder. MBForge metadata lives in `.mbforge/` (hidden):

```
my-project/
├── .mbforge/
│   ├── settings.json       # ProjectSettings
│   ├── index.json          # DocumentEntry index
│   ├── chroma_db/          # ChromaDB persistent client
│   ├── mol.db             # SQLite molecule database
│   ├── memories/          # Agent memory JSON files
│   └── trajectories/      # Tool call logs
├── papers/
│   ├── paper1.pdf
│   └── paper2.md
└── molecules/
    └── hit_compounds.sdf
```

---

## 6. Config System (Two Tiers)

### Global Config (`~/.config/MBForge/config.json`)

```
AppConfig
├── llm: ModelConfig
│   ├── provider: openai_compatible | anthropic | local
│   ├── base_url: http://localhost:8000/v1
│   ├── api_key: ...
│   ├── model_name: Qwen2.5-7B-Instruct
│   ├── max_tokens: 4096
│   └── temperature: 0.7
├── embed: EmbedConfig
│   ├── provider: sentence_transformers | openai | api
│   ├── model_name: BAAI/bge-small-zh-v1.5
│   ├── device: cpu | cuda
├── rerank: RerankConfig
│   ├── provider: sentence_transformers
│   ├── model_name: BAAI/bge-reranker-base
│   └── device: cpu | cuda
├── vlm: VLMConfig
│   └── ...
├── recent_projects: [...]
├── theme: dark | light
└── language: zh | en
```

### Project Config (`.mbforge/settings.json`)

```
ProjectSettings
├── name: MyProject
├── created_at: ISO timestamp
├── model_overrides: {...}    # Override global LLM/embedder per-project
├── workflow_toggles: {generation: false, docking: false, ...}
└── ...
```

**Priority:** Project-level overrides > Global config > Environment variables > Defaults.

---

## 7. Agent Tool Registry

Ten tools registered in `agent/tools.py`:

| Tool | Function | Description |
|------|----------|-------------|
| `search_knowledge` | `KnowledgeBase.hybrid_search()` | Semantic search with rerank |
| `search_molecules` | `MoleculeDatabase.search_by_*` | Search by SMILES, activity, source |
| `get_document` | `DocumentProcessor.process()` | Load document content |
| `get_document_summary` | `KnowledgeBase.get_document_overview()` | Get L1 overview |
| `list_project_files` | `Project.list_documents()` | List all indexed files |
| `get_molecule_details` | `MoleculeDatabase.get_molecule()` | Get full molecule record |
| `calculate_properties` | `MoleculeRecord.compute_properties()` | RDKit property calculation |
| `search_by_substructure` | *(placeholder)* | Substructure search |
| `get_recent_memories` | `MemoryManager.get_recent()` | Retrieve memory context |
| `save_note` | *(placeholder)* | Save user note |

---

## 8. Memory System

Based on TencentDB-Agent-Memory patterns, 6 memory types:

| Type | Source | TTL |
|------|--------|-----|
| User profile | Explicit / extracted from conversation | Long-term |
| Agent experience | Extracted after each session | Long-term |
| Project summary | Periodic summarization | Long-term |
| Recent context | Last N tool calls | Session |
| Entity knowledge | Document parsing | Long-term |
| Session summary | End-of-session extraction | Medium |

Memory injection: `MemoryManager.get_user_profile_text()` → `LayeredContext.inject_memory()` → system prompt layer.

---

## 9. Design Influences

- **Vault metaphor**: Obsidian — folder = project, `.obsidian/` = `.mbforge/`
- **ChromaDB integration**: Inspired by TencentDB-Agent-Memory architecture
- **ReAct agent**: OpenAI function calling + tool execution loop
- **Layered context**: Hierarchical context management (system → project → memory → history)
- **PDF parsing**: PyMuPDF ( Fitz ) for text + image extraction, LLM for structured summarization

---

## 10. Extension Points

### Adding a new LLM provider

1. Subclass `BaseLLM` in `models/`
2. Implement `chat()`, `chat_stream()`, `achat()`, `achat_stream()`
3. Add dispatch in `create_llm_from_config()`:

```python
if provider == "myprovider":
    from .my_llm import MyLLM
    return MyLLM(...)
```

### Adding a new Agent tool

1. Define function in `agent/tools.py`
2. Register: `ToolExecutor.registry.register(my_tool)`
3. Tool schema auto-exported via `to_openai_schemas()`

### Adding a workflow module

1. Create `workflow/mymodule.py` implementing `WorkflowBase`
2. Add toggle in `ProjectSettings`
3. Wire toggle in UI (`ui/dialogs.py` or `ui/main_window.py`)

### Replacing PyMuPDF with UniParser

`parser_io/ParserClient` wraps UniParser API. Replace `DocumentProcessor.process()` calls with `ParserClient.parse_and_wait()` in `PDFParserPipeline` to switch parsing backend.
