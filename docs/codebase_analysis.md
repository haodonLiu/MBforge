I have now read every Python file in the `src/mbforge/` directory tree. Here is the complete structured report.

---

# MBForge -- Complete Python Source Analysis

**Project root:** `C:\Users\10954\Desktop\MBForge`
**Total Python files:** 78

---

## 1. `src/mbforge/__init__.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\__init__.py`
- **Lines:** 9
- **Imports:** None
- **Module-level variables:** `__version__ = "0.1.0"`, `__all__ = ["__version__"]`
- **Classes:** None
- **Functions:** None
- **Logic:** Package root docstring declaring the project as a molecular knowledge base and AI workbench (Obsidian+Zotero-like for medicinal chemistry). Exports only the version string.

---

## 2. `src/mbforge/__main__.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\__main__.py`
- **Lines:** 6
- **Imports:** `.cli.main`
- **Module-level variables:** None
- **Classes:** None
- **Functions:** None
- **Logic:** Entry point for `python -m mbforge`. Delegates to `cli.main()` and exits with its return code.

---

## 3. `src/mbforge/cli.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\cli.py`
- **Lines:** 127
- **Imports:** Standard library: `argparse`, `sys`, `pathlib.Path`. Internal: `dotenv`, `.utils.logger.get_logger`, `.utils.logger.setup_logging`. Deferred: `.app.run_app`, `.core.project.Project`, `.core.knowledge_base.KnowledgeBase`, `.core.mol_database.MoleculeDatabase`, `.models.create_embedder_from_config`, `.models.create_llm_from_config`, `.parsers.pdf_parser.PDFParserPipeline`, `.utils.config.load_global_config`
- **Module-level variables:** `logger`
- **Functions:**
  - `main() -> int` (line 21): CLI entry. Sets up argparse with subcommands `gui`, `init`, `index`, and `--version`. Dispatches to the corresponding `_cmd_*` function.
  - `_cmd_gui(args) -> int` (line 55): Sets `MBFORGE_OPEN_PROJECT` env var if `--project` is given, then calls `run_app`.
  - `_cmd_init(args) -> int` (line 68): Resolves path, creates a new `Project` with optional name.
  - `_cmd_index(args) -> int` (line 80): Opens a project, loads config, creates embedder/LLM/KB/mol_db, builds `PDFParserPipeline`, scans files, and indexes all unindexed PDFs sequentially.
- **Logic:** Standard CLI with three subcommands. The `index` command reads global config, instantiates all model backends, and runs the full PDF parsing pipeline on each unindexed document in the project.

---

## 4. `src/mbforge/app.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\app.py`
- **Lines:** 56
- **Imports:** Standard library: `os`, `sys`. PyQt6: `Qt`, `QApplication`. Internal: `.ui.main_window.MainWindow`, `.utils.logger.setup_logging`. Deferred: `dotenv`.
- **Module-level variables:** None
- **Functions:**
  - `run_app(argv) -> int` (line 27): Configures high-DPI, initializes logging, creates `QApplication`, sets name/version/org/font, instantiates `MainWindow`, shows it, and enters the Qt event loop.
- **Logic:** Pure GUI bootstrap. Loads `.env` for HuggingFace/ModelScope cache paths, sets up PyQt6 application, and launches the main window.

---

## 5. `src/mbforge/csar_main.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\csar_main.py`
- **Lines:** 286
- **Imports:** Standard library: `argparse`, `logging`, `sys`, `pathlib.Path`. Internal: `mbforge.csar_io.reader.MoleculeReader`, `mbforge.csar_io.writer.MoleculeWriter`, `mbforge.clustering.fingerprinter.MolecularFingerprinter`, `mbforge.clustering.cluster.MolecularClusterer`, `mbforge.mcs.finder.MCSFinder`, `mbforge.sar.analyzer.SARAnalyzer`, `mbforge.csar_vis.renderer.SARRenderer`, `mbforge.csar_vis.renderer.PlotSettings`, `mbforge.molecules.models.MoleculeBatch`. Deferred: `mbforge.mcs.finder.find_substitution_positions`
- **Module-level variables:** `logger`
- **Functions:**
  - `parse_args() -> Namespace` (line 31): Defines CLI arguments for the CSAR workflow (input file, output dir, column names, clustering parameters, MCS timeout, visualization toggle, IC50 columns).
  - `run_workflow(input_file, output_dir, ...) -> None` (line 115): Complete SAR analysis pipeline: reads molecules via `MoleculeReader.read_batch`, converts to dict list, fingerprints and clusters with `MolecularClusterer`, finds MCS per cluster with `MCSFinder`, analyzes SAR with `SARAnalyzer`, generates visualizations with `SARRenderer` (summary, similarity matrix, per-cluster SAR path images), and saves CSV/SDF output.
  - `main() -> None` (line 260): Configures logging, parses args, calls `run_workflow`.
- **Logic:** The top-level CSAR (Compound Structure-Activity Relationship) workflow orchestrator. Reads molecular data, clusters by fingerprint similarity, finds MCS scaffolds per cluster, performs SAR analysis, generates publication-quality visualizations, and exports results.

---

## 6. `src/mbforge/agent/__init__.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\agent\__init__.py`
- **Lines:** 29
- **Imports:** `.agent.ProjectAgent`, `.archive_agent.ArchiveAgent`, `.context.LayeredContext`, `.executor.ToolExecutor`, `.memory_manager.MemoryManager`, `.memory_manager.MemoryEntry`, `.tools.ToolRegistry`, `.tools.tool`, `.trajectory.TrajectoryTracker`, `.trajectory.TrajectoryStep`
- **Logic:** Package init exporting all agent framework components.

---

## 7. `src/mbforge/agent/agent.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\agent\agent.py`
- **Lines:** 323
- **Imports:** Standard library: `json`, `pathlib.Path`, `typing`. Internal: `.context.LayeredContext`, `.executor.ToolExecutor`, `.memory_manager.MemoryManager`, `.trajectory.TrajectoryTracker`, `..models.base.BaseLLM`, `..models.base.Message`, `..utils.logger.get_logger`. Deferred: `..models.anthropic_llm.AnthropicLLM`, `..models.llm.OpenAILLM`
- **Module-level variables:** `logger`
- **Class `ProjectAgent` (line 32):**
  - **Attributes:** `DEFAULT_SYSTEM_PROMPT` (class), `llm`, `tool_executor`, `max_iterations`, `project_root`, `context`, `memory_manager`, `trajectory_tracker`
  - **Methods:**
    - `__init__(self, llm, tool_executor, system_prompt, max_iterations, project_root)` (line 49)
    - `_inject_tool_descriptions(self)` (line 79): Appends tool descriptions to system prompt.
    - `_inject_memories(self)` (line 97): Injects user profile and agent memory into context.
    - `set_project_context(self, project_name, project_path)` (line 108)
    - `chat(self, user_input) -> str` (line 114): Synchronous ReAct loop -- up to `max_iterations` rounds of LLM call + tool execution. If tools are available, requests function calling; parses response for tool calls; executes each tool, records trajectory, and loops. Returns final text answer.
    - `chat_stream(self, user_input)` (line 166): Streaming variant. Checks for tool needs first (single call), executes tools synchronously if needed, then streams the final answer via `llm.chat_stream`.
    - `extract_memory(self)` (line 219): Triggers automatic memory extraction from conversation history via LLM.
    - `_call_llm(self, messages)` (line 228): Basic LLM call.
    - `_call_llm_with_tools(self, messages, tools)` (line 232): Dispatches to `AnthropicLLM.call_with_tools` or `OpenAILLM.client.chat.completions.create` depending on LLM type; falls back to plain `chat` on error.
    - `_parse_response(self, response) -> tuple[str, List[Dict]]` (line 267): Handles Anthropic response objects (content blocks with text/tool_use), OpenAI response objects (choices[0].message with tool_calls), and plain strings.
    - `_execute_tool_call(self, tool_call) -> str` (line 311): Calls `tool_executor.registry.call(name, args)`.
    - `clear(self)` (line 320): Clears context history.
- **Logic:** The core Agent implementing a ReAct loop. On each user message, it builds layered context, calls the LLM (with tools if available), parses tool calls from the response, executes them via the ToolExecutor, records trajectory, and repeats until the LLM returns a direct answer or max iterations are reached. Supports both Anthropic and OpenAI function calling formats.

---

## 8. `src/mbforge/agent/context.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\agent\context.py`
- **Lines:** 211
- **Imports:** Standard library: `dataclasses`, `typing`. Internal: `..models.base.Message`, `..utils.logger.get_logger`
- **Module-level variables:** `logger`
- **Class `ContextLayer` (line 19, dataclass):**
  - Fields: `name`, `messages`, `priority`, `max_tokens`, `ephemeral`
  - Methods: `add(self, role, content, **kwargs)`, `clear(self)`
- **Class `LayeredContext` (line 36):**
  - **Attributes:** `max_history_rounds`, `max_total_tokens`, `_layers` (list of 4 ContextLayers: system/project/tools/history)
  - **Properties:** `_system`, `_project`, `_tools`, `_history`
  - **Methods:**
    - `__init__(self, system_prompt, max_history_rounds, max_total_tokens)` (line 46)
    - `set_system_prompt(self, prompt)` (line 85)
    - `set_project_context(self, context)` (line 90)
    - `update_project_context(self, context)` (line 96)
    - `clear_project_context(self)` (line 100)
    - `inject_memory(self, memory_text)` (line 103)
    - `inject_agent_memory(self, memory_text)` (line 109)
    - `inject_retrieval_trajectory(self, trajectory_text)` (line 115)
    - `add_tool_result(self, tool_name, result, tool_call_id)` (line 123)
    - `clear_tool_results(self)` (line 132)
    - `add_user_message(self, content)` (line 137)
    - `add_assistant_message(self, content, tool_calls)` (line 140)
    - `trim_history(self)` (line 143)
    - `clear_history(self)` (line 153)
    - `build_messages(self, include_tools, include_history) -> List[Message]` (line 161): Assembles messages from L0-L3 layers in priority order, validates roles.
    - `to_dict(self)` (line 193): Serializes (excludes ephemeral tools layer).
    - `from_dict(cls, data)` (line 202): Class method deserializer.
  - **Class variable:** `VALID_ROLES = {"system", "user", "assistant", "tool"}`
- **Logic:** Four-layer context management system. L0 (system prompt, permanent), L1 (project context + memories), L2 (tool results, ephemeral), L3 (conversation history, trimmable). `build_messages` assembles them in priority order for LLM consumption. Supports serialization/deserialization for persistence.

---

## 9. `src/mbforge/agent/executor.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\agent\executor.py`
- **Lines:** 345
- **Imports:** Standard library: `typing`. Internal: `.tools.ToolMixin`, `.tools.ToolRegistry`, `.tools.tool`, `..utils.helpers.truncate_text`, `..utils.logger.get_logger`. Deferred: `..core.knowledge_base.KnowledgeBase`, `..core.mol_database.MoleculeDatabase`, `..core.project.Project`
- **Module-level variables:** `logger`
- **Class `ToolExecutor` (line 22):**
  - **Methods:**
    - `__init__(self, project, knowledge_base, mol_db)` (line 28)
    - `_register_default_tools(self)` (line 40): Registers 10 tools via `ToolMixin.register_from_function`.
    - `search_knowledge_base(self, query, top_k) -> str` (line 74): Semantic search on KB, returns top results with truncated text.
    - `find_documents(self, keyword, doc_type, top_k) -> str` (line 108): Searches KB, then filters by L0 abstract/keywords/entity tags via `SummaryManager`.
    - `read_document_abstract(self, doc_id) -> str` (line 159): Returns L0 one-line summary.
    - `read_document_overview(self, doc_id) -> str` (line 180): Returns L1 structured overview.
    - `read_document_detail(self, doc_id, max_chars) -> str` (line 205): Returns full indexed content chunks.
    - `list_molecules(self, limit) -> str` (line 231): Lists molecules from mol_db.
    - `search_molecule_by_smiles(self, smiles) -> str` (line 257): Looks up molecule by SMILES.
    - `list_documents(self, doc_type) -> str` (line 285): Lists project documents.
    - `get_document_summary(self, doc_id) -> str` (line 310): Returns document metadata.
    - `get_project_info(self) -> str` (line 332): Returns project stats.
- **Logic:** Wraps the project's KnowledgeBase, MoleculeDatabase, and Project capabilities as LLM-callable tools with OpenAI function calling schemas. Each tool method is decorated with `@tool` for auto-registration.

---

## 10. `src/mbforge/agent/memory_manager.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\agent\memory_manager.py`
- **Lines:** 212
- **Imports:** Standard library: `json`, `dataclasses`, `datetime`, `pathlib.Path`, `typing`, `re`. Internal: `..utils.constants.MEMORY_DIR`, `..utils.constants.PROJECT_META_DIR`, `..utils.logger.get_logger`
- **Module-level variables:** `logger`
- **Class `MemoryEntry` (line 29, dataclass):**
  - Fields: `category`, `key`, `content`, `confidence`, `source`, `created_at`, `updated_at`, `access_count`
  - Methods: `to_dict(self)`, `from_dict(cls, data)`
- **Class `MemoryManager` (line 49):**
  - **Class variable:** `CATEGORIES = ["profile", "preferences", "entities", "events", "cases", "patterns"]`
  - **Methods:**
    - `__init__(self, project_root)` (line 54): Creates memory dir, loads all categories into cache.
    - `_category_path(self, category) -> Path` (line 61)
    - `_load_all(self)` (line 64): Loads each category's JSON file into `_cache`.
    - `_save_category(self, category)` (line 79)
    - `add(self, category, key, content, confidence, source)` (line 89): Upserts a memory entry.
    - `get(self, category, key) -> Optional[MemoryEntry]` (line 117)
    - `search(self, category, query) -> List[MemoryEntry]` (line 125): Substring match.
    - `list_category(self, category) -> List[MemoryEntry]` (line 134)
    - `delete(self, category, key) -> bool` (line 138)
    - `get_user_profile_text(self) -> str` (line 148): Returns formatted text for LLM injection (profile+preferences+entities).
    - `get_agent_memory_text(self) -> str` (line 159): Returns cases+patterns for LLM injection.
    - `extract_from_conversation(self, messages, llm)` (line 170): Uses LLM to analyze conversation history and auto-extract structured memories (JSON array of category/key/content/confidence).
- **Logic:** Six-category memory system (profile, preferences, entities, events, cases, patterns). Each category is stored as a JSON file in `.mbforge/memory/`. Supports CRUD, substring search, and LLM-driven automatic memory extraction from conversations.

---

## 11. `src/mbforge/agent/trajectory.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\agent\trajectory.py`
- **Lines:** 162
- **Imports:** Standard library: `json`, `dataclasses`, `datetime`, `pathlib.Path`, `typing`. Internal: `..utils.constants.PROJECT_META_DIR`, `..utils.constants.TRAJECTORY_DIR`, `..utils.constants.TRAJECTORY_FILE`, `..utils.constants.VIKING_SCHEME`, `..utils.logger.get_logger`
- **Module-level variables:** `logger`
- **Class `TrajectoryStep` (line 25, dataclass):**
  - Fields: `step_type`, `uri`, `query`, `result_count`, `top_results`, `duration_ms`, `timestamp`, `metadata`
  - Methods: `to_dict(self)`, `from_dict(cls, data)`
- **Class `TrajectoryTracker` (line 45):**
  - **Methods:**
    - `__init__(self, project_root)` (line 48)
    - `_load(self)` (line 55)
    - `save(self)` (line 65)
    - `add_step(self, step)` (line 75): Appends step, keeps last 500.
    - `record_search(self, query, result_count, top_results, duration_ms, metadata)` (line 82)
    - `record_navigate(self, path, reason, metadata)` (line 101)
    - `record_read(self, doc_id, level, metadata)` (line 115)
    - `record_tool(self, tool_name, arguments, result_summary, metadata)` (line 129)
    - `get_recent(self, limit) -> List[TrajectoryStep]` (line 146)
    - `get_summary(self) -> str` (line 149)
    - `clear(self)` (line 158)
- **Logic:** Records Agent retrieval/action steps as "viking://" URI-formatted trajectory entries. Persisted to `.mbforge/trajectory/trajectory.json`. Caps at 500 steps. Used for explainability and retrieval strategy optimization.

---

## 12. `src/mbforge/agent/tools.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\agent\tools.py`
- **Lines:** 132
- **Imports:** Standard library: `typing`. Internal: `..utils.logger.get_logger`
- **Module-level variables:** `logger`
- **Class `ToolInfo` (line 18):**
  - **Methods:**
    - `__init__(self, name, description, parameters_schema, func)` (line 21)
    - `to_openai_schema(self) -> Dict` (line 33): Generates OpenAI function calling JSON schema.
- **Class `ToolRegistry` (line 49):**
  - **Methods:**
    - `__init__(self)` (line 52)
    - `register(self, name, description, parameters_schema, func) -> ToolInfo` (line 55)
    - `get(self, name) -> Optional[ToolInfo]` (line 68)
    - `list_tools(self) -> List[ToolInfo]` (line 71)
    - `to_openai_schemas(self) -> List[Dict]` (line 74)
    - `call(self, name, arguments) -> str` (line 78): Invokes tool by name with kwargs, returns string result.
- **Function `tool(description, parameters)` (line 91):** Decorator that attaches `_tool_description` and `_tool_parameters` attributes to a function.
- **Class `ToolMixin` (line 114):**
  - **Static method:** `register_from_function(registry, func) -> ToolInfo` (line 126): Reads decorator attributes and registers.
- **Logic:** Tool registration framework. Tools are Python functions decorated with `@tool`, stored in a `ToolRegistry`, and can be exported as OpenAI-compatible function calling schemas.

---

## 13. `src/mbforge/agent/archive_agent.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\agent\archive_agent.py`
- **Lines:** 175
- **Imports:** Standard library: `json`, `threading`, `pathlib.Path`, `typing`. Internal: `..core.document.ExtractedContent`, `..core.todo_manager.TodoManager`, `..core.todo_manager.TodoStatus`, `..utils.helpers.split_text_chunks`, `..utils.logger.get_logger`
- **Module-level variables:** `logger`
- **Class `ArchiveAgent` (line 25):**
  - **Methods:**
    - `__init__(self, llm, knowledge_base, mol_db, project_root)` (line 28)
    - `run(self) -> Dict[str, Any]` (line 41): Iterates over DONE todo entries, ensures RAG indexing and generates summaries. Returns stats.
    - `run_async(self, on_done)` (line 70): Runs `run()` in a daemon thread.
    - `_archive_file(self, entry, out_dir) -> Dict` (line 87): For a single file: checks RAG index status, triggers indexing if missing, generates LLM summary if missing.
    - `_ensure_rag_indexed(self, entry, out_dir, index_data)` (line 111): Reads content.json, splits into chunks, indexes to KB.
    - `_generate_summary(self, entry, out_dir, index_data)` (line 133): Uses LLM to generate a structured summary (background, methods, results, molecules, activity data).
- **Logic:** Background agent that processes completed TODO entries. Ensures each processed file is indexed into the RAG knowledge base and has an LLM-generated summary. Runs asynchronously in a daemon thread.

---

## 14. `src/mbforge/core/__init__.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\core\__init__.py`
- **Lines:** 23
- **Logic:** Exports `Project`, `DocumentEntry`, `DocumentProcessor`, `ExtractedContent`, `KnowledgeBase`, `MoleculeDatabase`, `MoleculeRecord`, `ProjectSettings`, `DocumentSummary`, `SummaryManager`, `DocumentSummarizer`.

---

## 15. `src/mbforge/core/document.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\core\document.py`
- **Lines:** 125
- **Imports:** Standard library: `dataclasses`, `pathlib.Path`, `typing`. Deferred: `fitz` (PyMuPDF). Internal: `..utils.helpers.split_text_chunks`
- **Class `ExtractedContent` (line 18, dataclass):**
  - Fields: `text`, `metadata`, `molecules`, `images`, `tables`, `chunks`, `summary`
  - Methods: `to_dict(self)`
- **Class `DocumentProcessor` (line 41):**
  - **Class methods:**
    - `read_text(cls, path) -> str` (line 44)
    - `read_markdown(cls, path) -> str` (line 51)
    - `read_pdf_text(cls, path) -> str` (line 56): Uses PyMuPDF to extract text from all pages.
    - `extract_pdf_images(cls, path, output_dir) -> List[Path]` (line 67): Extracts embedded images from PDF pages.
    - `extract_pdf_tables(cls, path) -> List` (line 89): Stub (returns empty).
    - `process(cls, path, chunk_size, chunk_overlap) -> ExtractedContent` (line 100): Dispatches by extension (.pdf, .md, .txt, .json, .yaml, .yml), extracts text, and splits into chunks.
- **Logic:** Core document processing: reads various file formats, extracts text/images from PDFs via PyMuPDF, and chunks text for RAG indexing.

---

## 16. `src/mbforge/core/summarizer.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\core\summarizer.py`
- **Lines:** 203
- **Imports:** Standard library: `json`, `dataclasses`, `pathlib.Path`, `typing`, `re`, `collections.Counter`. Internal: `.document.ExtractedContent`, `..utils.constants.PROJECT_META_DIR`, `..utils.logger.get_logger`. Deferred: `..models.base.Message`
- **Module-level variables:** `SUMMARY_DIR = "summaries"`, `logger`
- **Class `DocumentSummary` (line 27, dataclass):**
  - Fields: `doc_id`, `l0_abstract`, `l1_overview`, `l2_detail_hint`, `keywords`, `entity_tags`
  - Methods: `to_dict(self)`, `from_dict(cls, data)`
- **Class `SummaryManager` (line 58):**
  - Methods: `__init__(project_root)`, `_summary_path(doc_id)`, `save(summary)`, `load(doc_id)`, `delete(doc_id)`, `list_all()`
- **Class `DocumentSummarizer` (line 101):**
  - Methods:
    - `__init__(self, llm)` (line 104)
    - `summarize(self, content, doc_id) -> DocumentSummary` (line 107): Generates L0 (one-sentence), L1 (structured overview) summaries via LLM, extracts keywords (frequency-based) and entity tags from molecule data.
    - `_generate_l0(self, text) -> str` (line 134): LLM prompt for 80-char summary.
    - `_generate_l1(self, text) -> str` (line 150): LLM prompt for structured 1500-char overview with 5 sections.
    - `_extract_keywords(self, text) -> list[str]` (line 174): Regex-based word extraction, stop word filtering, top-10 by frequency.
- **Logic:** Three-layer document summary system (L0: ~100 tokens one-line, L1: ~2000 tokens structured overview, L2: full content pointer). Uses LLM for L0/L1 generation and simple frequency analysis for keywords. Stored as JSON in `.mbforge/summaries/`.

---

## 17. `src/mbforge/core/knowledge_base.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\core\knowledge_base.py`
- **Lines:** 223
- **Imports:** Standard library: `pathlib.Path`, `typing`. Third-party: `chromadb`, `chromadb.config.Settings`. Internal: `.document.ExtractedContent`, `.summarizer.SummaryManager`, `..utils.constants.KB_COLLECTION_DOCS`, `..utils.constants.PROJECT_META_DIR`, `..utils.logger.get_logger`
- **Module-level variables:** `logger`
- **Class `KnowledgeBase` (line 24):**
  - **Methods:**
    - `__init__(self, project_root, embedder)` (line 27): Creates ChromaDB PersistentClient, gets/creates collection with cosine distance.
    - `_get_summary(self, doc_id)` (line 43): Lazy-loads SummaryManager.
    - `close(self)` (line 49): Releases references.
    - `index_document(self, doc_id, content, metadata)` (line 56): Chunks document, generates embeddings via embedder, adds to ChromaDB collection with chunk IDs and metadata.
    - `remove_document(self, doc_id)` (line 105): Deletes by doc_id filter.
    - `search(self, query, top_k, filter_dict) -> List[Dict]` (line 110): Semantic search using query embedding or ChromaDB's built-in text search fallback.
    - `hybrid_search(self, query, top_k, reranker) -> List[Dict]` (line 148): Search + rerank pipeline.
    - `get_stats(self) -> Dict` (line 168)
    - `search_by_directory(self, query, directory_prefix, top_k) -> List[Dict]` (line 176): Directory-scoped search.
    - `get_document_abstract(self, doc_id) -> Optional[str]` (line 196)
    - `get_document_overview(self, doc_id) -> Optional[str]` (line 203)
    - `get_document_keywords(self, doc_id) -> List[str]` (line 210)
    - `list_document_entities(self, doc_id) -> List[str]` (line 217)
- **Logic:** ChromaDB-backed vector store. Documents are chunked, embedded, and indexed. Supports semantic search (with optional embedding model), hybrid search (search + rerank), directory-scoped search, and document summary retrieval via SummaryManager.

---

## 18. `src/mbforge/core/memory.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\core\memory.py`
- **Lines:** 57
- **Imports:** Standard library: `json`, `pathlib.Path`, `typing`. Internal: `..utils.constants.MEMORY_DIR`, `..utils.constants.PROJECT_META_DIR`, `..utils.logger.get_logger`
- **Module-level variables:** `MEMORY_FILE = "conversation.json"`, `logger`
- **Class `ProjectMemory` (line 21):**
  - Methods: `__init__(project_root)`, `save_dict(data)`, `load_dict() -> Optional[Dict]`, `clear()`
- **Logic:** Simple JSON-based conversation memory persistence. Stores/loads a single dict to `.mbforge/memory/conversation.json`. Independent of the agent module -- just handles serialization.

---

## 19. `src/mbforge/core/mol_database.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\core\mol_database.py`
- **Lines:** 236
- **Imports:** Standard library: `json`, `sqlite3`, `dataclasses`, `pathlib.Path`, `typing`. Deferred: `rdkit.Chem`, `rdkit.Chem.Descriptors`, `rdkit.Chem.Draw`, `rdkit.Chem.AllChem`. Internal: `..utils.constants.MOL_DB_FILENAME`, `..utils.constants.PROJECT_META_DIR`
- **Class `MoleculeRecord` (line 27, dataclass):**
  - Fields: `mol_id`, `smiles`, `name`, `source_doc`, `activity`, `activity_type`, `units`, `properties`, `tags`, `notes`
  - Methods: `to_dict(self)`, `from_dict(cls, data)`, `mol` (property, returns RDKit Mol), `compute_properties(self) -> Dict`
- **Class `MoleculeDatabase` (line 95):**
  - **Class variable:** `SCHEMA` -- SQLite schema with `molecules` table, indexes on smiles/source/activity, and FTS5 virtual table `mol_search`.
  - **Methods:**
    - `__init__(self, project_root)` (line 120): Opens SQLite DB, initializes schema.
    - `_init_db(self)` (line 128)
    - `add_molecule(self, record)` (line 132): INSERT OR REPLACE, auto-computes properties if empty.
    - `get_molecule(self, mol_id)` (line 163)
    - `search_by_smiles(self, smiles)` (line 171)
    - `search_by_source(self, doc_id)` (line 179)
    - `search_by_activity_range(self, min_val, max_val, activity_type)` (line 185)
    - `list_all(self, limit)` (line 200)
    - `delete_molecule(self, mol_id)` (line 206)
    - `get_stats(self)` (line 210)
    - `_row_to_record(self, row) -> MoleculeRecord` (line 220)
    - `close(self)` (line 226)
    - Context manager support: `__enter__`, `__exit__`
- **Logic:** SQLite-backed molecule database with RDKit property computation (MW, LogP, HBD, HBA, TPSA, rotatable bonds). Supports full-text search via FTS5, CRUD operations, activity-range queries, and auto-computation of molecular properties on insert.

---

## 20. `src/mbforge/core/project.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\core\project.py`
- **Lines:** 247
- **Imports:** Standard library: `json`, `datetime`, `pathlib.Path`, `typing`. Internal: `.settings.ProjectSettings`, `..utils.constants.PROJECT_META_DIR`, `..utils.constants.SUPPORTED_DOC_EXTS`, `..utils.constants.SUPPORTED_MOL_EXTS`, `..utils.helpers.generate_uuid`, `..utils.helpers.sha256_file`, `..utils.logger.get_logger`
- **Module-level variables:** `logger`
- **Class `DocumentEntry` (line 22):**
  - Methods: `__init__(path, doc_id, doc_type, title, indexed)`, `_detect_type(path)` (static), `to_dict(self)`, `from_dict(cls, data, project_root)`
- **Class `Project` (line 92):**
  - **Methods:**
    - `__init__(self, root)` (line 95): Resolves root, loads settings, loads index from `.mbforge/index.json`.
    - `name` (property, line 103)
    - `_index_path(self)` (line 107)
    - `_load_index(self)` (line 110)
    - `_save_index(self)` (line 123)
    - `scan_files(self) -> List[DocumentEntry]` (line 135): Recursively scans project root for supported extensions, skipping `.mbforge/` and hidden dirs. Creates/updates entries, computes SHA256 only when mtime changes, removes deleted files.
    - `get_document(self, doc_id)` (line 173)
    - `get_document_by_path(self, path)` (line 176)
    - `add_file(self, path) -> DocumentEntry` (line 183)
    - `remove_document(self, doc_id)` (line 200)
    - `list_documents(self, doc_type)` (line 209)
    - `save_settings(self)` (line 215)
    - `create(cls, root, name) -> Project` (line 221): Creates `.mbforge/` dir, initializes settings.
    - `open(cls, root) -> Optional[Project]` (line 235)
    - `is_valid_project(cls, root) -> bool` (line 244)
- **Logic:** Vault-style project management (like Obsidian). A project is a directory with a `.mbforge/` hidden folder storing index.json, settings.json, and all metadata. File scanning discovers documents and molecule files, computes content hashes for change detection, and maintains a JSON index.

---

## 21. `src/mbforge/core/settings.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\core\settings.py`
- **Lines:** 70
- **Imports:** Standard library: `json`, `dataclasses`, `pathlib.Path`, `typing`. Internal: `..utils.constants.PROJECT_META_DIR`, `..utils.constants.SETTINGS_FILE`
- **Class `ProjectSettings` (line 14, dataclass):**
  - Fields: `name`, `description`, `created_at`, `llm_model`, `embed_model`, `auto_index`, `auto_process`, `pdf_ocr_enabled`, `pdf_extract_molecules`, `workflows_enabled` (dict with generation/docking/qsar/md flags)
  - Methods: `to_dict(self)`, `from_dict(cls, data)`, `load(cls, project_root)`, `save(self, project_root)`
- **Logic:** Per-project settings stored as JSON in `.mbforge/settings.json`. Controls auto-indexing, auto-processing, workflow toggles, and model selections.

---

## 22. `src/mbforge/core/todo_manager.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\core\todo_manager.py`
- **Lines:** 247
- **Imports:** Standard library: `json`, `shutil`, `threading`, `dataclasses`, `datetime`, `enum`, `pathlib.Path`, `typing`. Internal: `..utils.constants.OUTPUT_DIR`, `..utils.constants.PROJECT_META_DIR`, `..utils.constants.TODO_FILE`, `..utils.helpers.generate_uuid`, `..utils.logger.get_logger`
- **Module-level variables:** `logger`
- **Enum `TodoStatus` (line 26):** `PENDING`, `PROCESSING`, `DONE`, `FAILED`
- **Class `TodoEntry` (line 33, dataclass):**
  - Fields: `doc_id`, `filename`, `source_path`, `status`, `added_at`, `processed_at`, `error`, `output_dir`
  - Methods: `to_dict(self)`, `from_dict(cls, data)`
- **Class `TodoManager` (line 53):**
  - **Methods:**
    - `__init__(self, project_root)` (line 56)
    - `_load(self)` (line 67)
    - `save(self)` (line 77)
    - `add_file(self, filename, source_rel_path) -> TodoEntry` (line 88): Deduplicates by source_path.
    - `get_pending(self) -> List[TodoEntry]` (line 106)
    - `get_all(self)` (line 110)
    - `get_entry(self, doc_id)` (line 114)
    - `update_status(self, doc_id, status, error)` (line 121)
    - `get_output_path(self, doc_id) -> Path` (line 133)
    - `remove_entry(self, doc_id) -> bool` (line 137)
    - `clear_done(self) -> int` (line 146)
    - `process_next(self, file_processor) -> Optional[TodoEntry]` (line 157): Takes the next PENDING entry, calls `file_processor(entry, source_path, output_dir)`, saves result to `output/<doc_id>/index.json`, updates status.
    - `process_all(self, file_processor, on_progress)` (line 196): Synchronous batch.
    - `process_all_async(self, file_processor, on_progress, on_done)` (line 214): Threaded batch with restart-on-new-items support.
  - **Properties:** `is_processing`
- **Logic:** File processing queue. Files are imported into `raw/`, added to the TODO queue, and processed one-by-one or in batch. Each file gets an output directory `output/<doc_id>/`. Supports sync and async processing with progress callbacks.

---

## 23. `src/mbforge/csar_io/__init__.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\csar_io\__init__.py`
- **Lines:** 52
- **Logic:** Exports `PubChemClient`, `NCICIRClient`, `ChemicalAPIClient`, `CompoundProperties`, `CompoundInfo`, `APIClientError`, `CASResolver`, `CASResolverError`, `MoleculeReader`, `MoleculeReadError`, `MoleculeWriter`, `MoleculeWriteError`, `Molecule`, `MoleculeBatch`.

---

## 24. `src/mbforge/csar_io/api_client.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\csar_io\api_client.py`
- **Lines:** 829
- **Imports:** Standard library: `json`, `logging`, `time`, `urllib.error`, `urllib.parse`, `urllib.request`, `dataclasses`, `typing`. Internal: `re` (in `_extract_cas_from_synonyms`)
- **Module-level variables:** `PUBCHEM_COMMON_PROPERTIES` (tuple of PubChem property names), `logger`
- **Class `APIClientError(Exception)` (line 42)**
- **Class `CompoundProperties` (line 51, dataclass):** 18 optional fields (cid, molecular_formula, molecular_weight, canonical_smiles, etc.). Method: `to_dict(self)`.
- **Class `CompoundInfo` (line 101, dataclass):** Fields: cid, name, cas, synonyms, properties, source, raw_data. Methods: `to_dict(self)`.
- **Class `_BaseAPIClient` (line 135):** Base with `_get(url, accept)` (HTTP GET with content-type dispatch), `_sleep()`.
- **Class `PubChemClient(_BaseAPIClient)` (line 197):**
  - Methods: `_build_property_url`, `get_properties`, `get_properties_batch` (POST batch, max 100), `_get_properties_batch_post`, `_identifier_matches` (static), `_parse_properties` (static), `get_synonyms`, `get_cid`, `get_compound_info` (combines properties+synonyms+CAS), `get_sdf`, `search_by_name`
- **Class `NCICIRClient(_BaseAPIClient)` (line 520):**
  - Methods: `convert(identifier, input_format, output_format)`, `get_names`, `get_iupac_name`, `get_inchi`, `get_inchikey`, `get_cas`, `get_image`
- **Class `ChemicalAPIClient` (line 660):** Unified client combining PubChem + NCI CIR.
  - Methods: `get_compound_info` (tries PubChem, falls back to NCI CIR), `_get_info_from_nci_cir`, `get_properties_batch`, `convert_identifier`
- **Standalone functions:** `_to_float(value)`, `_to_int(value)`, `_extract_cas_from_synonyms(synonyms)`
- **Logic:** Full chemical database API client suite. PubChem PUG REST for properties/synonyms/CID/SDF/name search. NCI CIR for identifier conversion (SMILES->CAS, InChI, names, images). Unified `ChemicalAPIClient` with automatic fallback. Batch processing with rate limiting.

---

## 25. `src/mbforge/csar_io/cas_resolver.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\csar_io\cas_resolver.py`
- **Lines:** 290
- **Imports:** Standard library: `json`, `logging`, `re`, `time`, `urllib.error`, `urllib.parse`, `urllib.request`, `typing`
- **Module-level variables:** `_CAS_PATTERN` (regex for CAS numbers), `logger`
- **Class `CASResolverError(Exception)` (line 33)**
- **Class `CASResolver` (line 42):**
  - Methods: `__init__(timeout, delay)`, `validate_cas(cas_number)` (static, check digit algorithm), `_canonicalize_smiles(smiles)` (static, Open Babel), `_query_nci_cir(smiles)`, `_query_pubchem(smiles)`, `resolve(smiles, source, canonicalize)`, `resolve_batch(smiles_list, source, canonicalize)`
- **Logic:** SMILES-to-CAS resolution using NCI CIR (primary) and PubChem (fallback). Includes CAS check digit validation, optional SMILES canonicalization via Open Babel, and batch processing with rate limiting.

---

## 26. `src/mbforge/csar_io/reader.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\csar_io\reader.py`
- **Lines:** 396
- **Imports:** Standard library: `logging`, `pathlib.Path`, `typing`. Third-party: `pandas`, `rdkit.Chem`, `rdkit.Chem.PandasTools`. Internal: `..clustering.fingerprinter.MolecularFingerprinter`, `..molecules.schema.Molecule`, `..molecules.schema.MoleculeBatch`
- **Module-level variables:** `logger`
- **Class `MoleculeReadError(Exception)` (line 33)**
- **Class `MoleculeReader` (line 42):**
  - **Methods:**
    - `__init__(smiles_column, name_column, activity_column, cas_column)` (line 54)
    - `read_sdf(path) -> List[Dict]` (line 75): Uses `ForwardSDMolSupplier`, extracts name/SMILES/properties/CAS.
    - `read_excel(path, sheet_name, ic50_nm_column, ic50_um_column, deduplicate) -> List[Dict]` (line 129): Merges nM/uM IC50 columns, deduplicates by SMILES (averages activity), parses SMILES to RDKit Mol.
    - `read_csv(path) -> List[Dict]` (line 248)
    - `read_entries(path, **kwargs) -> List[Molecule]` (line 308): Type-safe version returning `Molecule` objects.
    - `read_batch(path, **kwargs) -> MoleculeBatch` (line 345): Returns `MoleculeBatch` container.
    - `read(path, **kwargs) -> List[Dict]` (line 368): Auto-detects format by extension.
- **Logic:** Multi-format molecule reader. SDF via RDKit supplier, Excel/CSV via pandas with SMILES column parsing, automatic IC50 unit merging and SMILES deduplication. Outputs either legacy dicts or typed `Molecule`/`MoleculeBatch` objects.

---

## 27. `src/mbforge/csar_io/writer.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\csar_io\writer.py`
- **Lines:** 227
- **Imports:** Standard library: `logging`, `pathlib.Path`, `typing`. Third-party: `pandas`, `rdkit.Chem`, `rdkit.Chem.AllChem`, `rdkit.Chem.Descriptors`. Internal: `..molecules.schema.Molecule`, `..molecules.schema.MoleculeBatch`
- **Module-level variables:** `logger`
- **Class `MoleculeWriteError(Exception)` (line 32)**
- **Class `MoleculeWriter` (line 41):**
  - **Methods:**
    - `write_sdf(molecules, path)` (line 48): Writes mol objects with properties via `SDWriter`.
    - `write_csv(molecules, path)` (line 79): Exports Name/SMILES/NumAtoms/NumBonds/MW/LogP/Activity/CAS via pandas.
    - `write_excel(molecules, path)` (line 128)
    - `write_molecules_csv(molecules, path)` (line 174): Molecule list -> MoleculeBatch -> CSV.
    - `write_molecules_sdf(molecules, path)` (line 192)
    - `write_molecules_excel(molecules, path)` (line 210)
- **Logic:** Multi-format molecule writer supporting legacy dict format and typed `Molecule`/`MoleculeBatch` objects. Auto-computes RDKit descriptors for CSV/Excel output.

---

## 28. `src/mbforge/csar_vis/__init__.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\csar_vis\__init__.py`
- **Lines:** 32
- **Logic:** Exports `SARRenderer`, `RenderError`.

---

## 29. `src/mbforge/csar_vis/renderer.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\csar_vis\renderer.py`
- **Lines:** 688
- **Imports:** Standard library: `io`, `logging`, `pathlib.Path`, `typing`, `dataclasses`. Third-party: `numpy`, `matplotlib.pyplot`, `matplotlib.patches`, `PIL.Image`, `rdkit.Chem`, `rdkit.Chem.AllChem`, `rdkit.Chem.Draw`, `rdkit.Chem.Draw.rdMolDraw2D`. Internal: `..mcs.finder.find_substitution_positions`, `..mcs.finder.create_marked_scaffold`, `..mcs.finder.ScaffoldInfo`, `..mcs.finder.SubstituentInfo`, `.utils.render_substituent_image`, `.utils.combine_scaffold_and_table`, `.utils.extract_substituent`, `.utils.create_sar_table_image`
- **Module-level variables:** `logger`
- **Class `RenderError(Exception)` (line 54)**
- **Class `PlotSettings` (line 63, dataclass):** figure_size, dpi, title_fontsize, label_fontsize, tick_fontsize, color_scheme, show_labels, save_format.
- **Class `SARRenderer` (line 90):**
  - **Methods:**
    - `__init__(settings)` (line 110)
    - `render_mcs(mcs_mol, output_path, title)` (line 118): Renders MCS structure via `Draw.MolToMPL`.
    - `render_cluster_activity(cluster_id, molecules, output_path, mcs_mol)` (line 152): Histogram + MCS scaffold side-by-side.
    - `render_sar_summary(sar_results, output_path)` (line 200): Bar chart of mean activities + scatter of size vs activity.
    - `render_similarity_matrix(sim_matrix, output_path, labels)` (line 251): Tanimoto heatmap.
    - `render_mols_with_activities(molecules, output_path, mols_per_row, legends)` (line 289): Grid image with activity legends.
    - `render_sar_table_image(scaffold_info, molecules, output_path, scaffold_size, sub_size)` (line 330): Generates SAR table images, splitting into pairs if >2 R-groups.
    - `_render_single_table(...)` (line 406): Core SAR table renderer -- matches molecules to scaffold, extracts substituents, creates table image, combines with scaffold.
    - `render_sar_path_image(...)` (line 486): Groups molecules by modification path (R1 fixed, R2 varies), generates per-path tables.
    - `_group_by_path(mol_data_list, num_r)` (line 607): Groups by R1 value for path visualization.
    - `_create_table_image(rows, col_labels, num_r_groups, sub_size)` (line 665): Delegates to `utils.create_sar_table_image`.
- **Logic:** Comprehensive SAR visualization suite using matplotlib + RDKit + PIL. Generates MCS structure plots, activity distribution histograms, SAR summary charts, similarity matrix heatmaps, molecule grids, and detailed SAR table images showing scaffold + substituent combinations with activity color coding.

---

## 30. `src/mbforge/csar_vis/sar_table.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\csar_vis\sar_table.py`
- **Lines:** 59
- **Imports:** Standard library: `logging`, `typing`. Third-party: `PIL.Image`. Internal: `.utils.create_sar_table_image`, `.utils.get_activity_color`, `.utils.SUBSTITUENT_SIZE`
- **Module-level variables:** `logger`
- **Function `create_substituent_table_image(rows, col_labels, activity_col_index, size)` (line 33):** Backward-compatible wrapper around `utils.create_sar_table_image` with activity colors enabled.
- **Logic:** Thin compatibility wrapper preserving the old API while delegating to the unified `utils.create_sar_table_image`.

---

## 31. `src/mbforge/csar_vis/utils.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\csar_vis\utils.py`
- **Lines:** 290
- **Imports:** Standard library: `io`, `logging`, `typing`. Third-party: `PIL.Image`, `PIL.ImageDraw`, `PIL.ImageFont`, `rdkit.Chem`, `rdkit.Chem.AllChem`, `rdkit.Chem.Draw.rdMolDraw2D`
- **Module-level variables:** `SUBSTITUENT_SIZE = (80, 60)`, `BORDER_COLOR`, `TEXT_COLOR`, `logger`
- **Functions:**
  - `render_substituent_image(mol, size) -> Optional[Image]` (line 22): Renders molecule via Cairo draw2D.
  - `combine_scaffold_and_table(scaffold_img, table_img, title, fontsize) -> Image` (line 55): Stacks scaffold image + title + table vertically.
  - `get_activity_color(activity) -> Tuple[int,int,int]` (line 106): Maps IC50 nM to green-yellow-red gradient.
  - `extract_substituent(mol, attachment_atom_idx, sub_atom_idx) -> Tuple[Optional[Mol], str]` (line 138): BFS extraction of substituent atoms.
  - `create_sar_table_image(rows, col_labels, sub_size, activity_col_index, use_activity_colors) -> Image` (line 182): Unified SAR table renderer with header row, zebra striping, activity color backgrounds, and image/text cell support.
- **Logic:** Shared visualization utilities. Substituent rendering via RDKit Cairo, scaffold+table image composition, activity-to-color mapping, BFS substituent extraction, and the core SAR table image generator used by both `renderer.py` and `sar_table.py`.

---

## 32. `src/mbforge/mcs/__init__.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\mcs\__init__.py`
- **Lines:** 33
- **Logic:** Exports `MCSFinder`, `MCSError`, `MCSResult`.

---

## 33. `src/mbforge/mcs/finder.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\mcs\finder.py`
- **Lines:** 556
- **Imports:** Standard library: `logging`, `typing`, `dataclasses`, `datetime`. Third-party: `rdkit.Chem`, `rdkit.Chem.rdFMCS`, `rdkit.Chem.Draw.rdMolDraw2D`
- **Module-level variables:** `logger`
- **Class `MCSError(Exception)` (line 41)**
- **Class `MCSResult` (line 50, dataclass):** mcs_mol, smiles, num_atoms, num_bonds, smiles_a, smiles_b, bond_matches, atom_matches, score.
- **Class `MCSFinder` (line 79):**
  - Methods: `__init__(timeout, verbose)`, `find_mcs(molecules, threshold) -> Optional[MCSResult]` (pairwise comparison strategy for >2 molecules), `_find_mcs_pair(mol_a, smiles_a, mol_b, smiles_b)` (uses `rdFMCS.FindMCS` with ring constraints), `find_mcs_for_clusters(clusters) -> Dict[int, Optional[MCSResult]]`
- **Class `SubstituentInfo` (line 292, dataclass):** position_idx, substituent_smiles, substituent_mol, mol_name, activity.
- **Class `ScaffoldInfo` (line 313, dataclass):** scaffold_mol, scaffold_smiles, r_positions (Dict[int, List[SubstituentInfo]]), num_r_groups.
- **Standalone functions:**
  - `find_substitution_positions(mcs_mol, molecules) -> Optional[ScaffoldInfo]` (line 332): Identifies R-group positions on MCS scaffold by matching molecules and extracting non-MCS substituents via BFS.
  - `_extract_substituent(mol, attachment_atom_idx, sub_atom_idx)` (line 407): BFS atom traversal + `MolFragmentToSmiles`.
  - `create_marked_scaffold(scaffold_info, size) -> bytes` (line 455): Renders scaffold with R1/R2 labels via Cairo.
- **CLI entry** (line 516): argparse for standalone MCS finding.
- **Logic:** Maximum Common Substructure finder. For 2 molecules, uses `rdFMCS.FindMCS` directly. For >2, uses pairwise comparison with best-score selection. Includes timeout protection. Also provides scaffold R-group position identification and labeled scaffold rendering.

---

## 34. `src/mbforge/molecules/__init__.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\molecules\__init__.py`
- **Lines:** 70
- **Logic:** Exports all molecule processing components: `Molecule`, `MoleculeEntry`, `MoleculeBatch`, `MoleculeDescriptorCalculator`, `DescriptorSet`, filters, `MoleculeStandardizer`, fragmenters, `SubstructureMatcher`, `SMARTSQuery`.

---

## 35. `src/mbforge/molecules/descriptors.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\molecules\descriptors.py`
- **Lines:** 380
- **Imports:** Standard library: `logging`, `dataclasses`, `enum`, `typing`. Third-party: `numpy`, `rdkit.Chem`, `rdkit.Chem.Descriptors`, `rdkit.Chem.GraphDescriptors`, `rdkit.Chem.MolSurf`, `rdkit.Chem.Lipinski`, `rdkit.Chem.rdMolDescriptors`, `rdkit.Chem.AllChem`, `rdkit.Chem.Descriptors3D`
- **Module-level variables:** `logger`
- **Enum `DescriptorSet` (line 31):** BASIC, LIPINSKI, TOPOLOGICAL, ELECTRONIC, ALL_2D, MORGAN_FP, ALL_3D, CUSTOM.
- **Class `DescriptorResult` (line 47, dataclass):** values, mol, success, errors. Methods: `get(name, default)`, `to_dict()`, `to_array(names)`.
- **Class `MoleculeDescriptorCalculator` (line 100):**
  - **Class variables:** `_DESCRIPTOR_REGISTRY` (dict of named sets mapping to (name, callable) lists), `_ALL_2D_DESCRIPTORS` (44 descriptors), `_3D_DESCRIPTORS` (10 descriptors).
  - **Methods:**
    - `__init__(descriptor_set, custom_descriptors, include_3d)` (line 228)
    - `_build_descriptor_list(self)` (line 248)
    - `compute(self, mol) -> DescriptorResult` (line 275): Iterates descriptors, calls each, catches errors per-descriptor.
    - `compute_batch(self, molecules, names) -> List[DescriptorResult]` (line 303)
    - `compute_molecule_entry(self, entry) -> DescriptorResult` (line 327)
    - `available_descriptors(self) -> List[str]` (line 338)
    - `add_descriptor(self, name, func)` (line 346)
    - `remove_descriptor(self, name) -> bool` (line 356)
    - `list_builtin_sets() -> List[str]` (static, line 369)
- **Logic:** Comprehensive molecular descriptor calculator supporting 7 preset sets (basic, lipinski, topological, electronic, all_2d, morgan_fp, all_3d) plus custom descriptors. Computes per-descriptor with error isolation. Returns results as dict, numpy array, or structured object.

---

## 36. `src/mbforge/molecules/filters.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\molecules\filters.py`
- **Lines:** 574
- **Imports:** Standard library: `logging`, `abc`, `dataclasses`, `typing`. Third-party: `rdkit.Chem`, `rdkit.Chem.Descriptors`, `rdkit.Chem.Lipinski`, `rdkit.Chem.rdMolDescriptors`, `rdkit.Chem.FilterCatalog.FilterCatalog`, `rdkit.Chem.FilterCatalog.FilterCatalogParams`
- **Module-level variables:** `logger`
- **Class `FilterResult` (line 33, dataclass):** passed, reasons, details. Supports `__bool__`.
- **Class `MoleculeFilter` (line 52, ABC):** Abstract with `filter(mol) -> FilterResult`, `accept(mol) -> bool`, `filter_batch(molecules, names) -> List[FilterResult]`.
- **Concrete filters:**
  - `LipinskiFilter` (line 104): MW<=500, LogP<=5, HBD<=5, HBA<=10, optional rotatable bonds<=10. Configurable max_violations (default 1).
  - `VeberFilter` (line 186): Rotatable bonds<=10, TPSA<=140 or HBD+HBA<=12.
  - `PAINSFilter` (line 252): Uses RDKit FilterCatalog PAINS detection.
  - `ToxicityFilter` (line 310): Uses BRENK catalog.
  - `MolecularWeightFilter` (line 341): Min/max MW range.
  - `RingCountFilter` (line 383): Min/max ring count.
  - `CustomFilter` (line 425): Predicate-based.
  - `CompositeFilter` (line 462): AND/OR composition of multiple filters.
- **Factory functions:**
  - `drug_likeness_filter(max_lipinski_violations, include_veber, include_pains) -> CompositeFilter` (line 526)
  - `lead_likeness_filter() -> CompositeFilter` (line 551): MW 250-350, LogP 1-3, 1-3 rings, strict Lipinski.
- **Logic:** Comprehensive molecular filtering framework. Abstract base class with 7 concrete filter implementations covering drug-likeness (Lipinski, Veber), assay interference (PAINS), toxicity (BRENK), size, and ring count. Composable via CompositeFilter with AND/OR logic.

---

## 37. `src/mbforge/molecules/fragment.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\molecules\fragment.py`
- **Lines:** 539
- **Imports:** Standard library: `logging`, `dataclasses`, `typing`. Third-party: `rdkit.Chem`, `rdkit.Chem.AllChem`, `rdkit.Chem.BRICS`, `rdkit.Chem.FragmentCatalog`, `rdkit.Chem.Recap`, `rdkit.Chem.Scaffolds.MurckoScaffold`
- **Module-level variables:** `logger`
- **Class `FragmentInfo` (line 30, dataclass):** smarts, smiles, mol, atom_indices, bond_indices.
- **Class `ScaffoldInfo` (line 52, dataclass):** scaffold_mol, scaffold_smiles, num_rings, num_atoms, original_smiles.
- **Class `ScaffoldAnalyzer` (line 71):**
  - Methods: `get_murcko_scaffold(mol, include_chirality)`, `get_murcko_scaffold_smiles(mol, include_chirality)`, `get_generic_scaffold(mol)` (all atoms C, all bonds single), `get_scaffold_info(mol, include_chirality)`, `group_by_scaffold(molecules, names, include_chirality)`, `get_scaffold_hierarchy(mol)` (3-level: original -> Murcko -> generic).
- **Class `RECAPFragmenter` (line 261):**
  - Methods: `fragment(mol) -> List[FragmentInfo]`, `_extract_fragments_from_tree(node)` (recursive), `fragment_batch(molecules, names)`.
- **Class `BRICSFragmenter` (line 331):**
  - Methods: `fragment(mol) -> List[FragmentInfo]`, `get_fragment_smiles(mol)`, `fragment_batch(molecules, names)`.
- **Class `RGroupAnalyzer` (line 416):**
  - Methods: `__init__(timeout)`, `find_r_groups(scaffold, mol) -> List[FragmentInfo]`, `_extract_r_group_fragment(mol, start_atom, scaffold_atoms)` (BFS + EditableMol subgraph extraction).
- **Logic:** Molecular decomposition and scaffold analysis. Murcko scaffold extraction (3 hierarchy levels), RECAP retrosynthetic fragmentation (11 bond types), BRICS combinatorial fragmentation (16 bond types), and R-group analysis via scaffold substructure matching + BFS.

---

## 38. `src/mbforge/molecules/matcher.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\molecules\matcher.py`
- **Lines:** 487
- **Imports:** Standard library: `logging`, `dataclasses`, `typing`. Third-party: `numpy`, `rdkit.Chem`, `rdkit.Chem.AllChem`, `rdkit.Chem.rdFMCS`, `rdkit.Chem.rdMolDescriptors`
- **Module-level variables:** `logger`
- **Class `MatchResult` (line 29, dataclass):** matched, query, target, atom_matches, bond_matches, match_count. Supports `__bool__`.
- **Class `SubstructureMatcher` (line 52):**
  - Methods: `__init__(use_chirality)`, `has_substruct(mol, pattern)`, `count_substruct_matches(mol, pattern, uniquify)`, `find_substructure_matches(mol, pattern, uniquify) -> MatchResult`, `find_largest_common_substructure(mol1, mol2, timeout)`, `tanimoto_similarity(mol1, mol2, radius, n_bits)`, `dice_similarity(mol1, mol2, radius, n_bits)`, `pairwise_similarity_matrix(molecules, radius, n_bits) -> np.ndarray`, `find_similar_molecules(query, molecules, threshold, top_n)`, `_to_mol(pattern)` (SMARTS then SMILES parsing).
- **Class `SMARTSQuery` (line 323):**
  - Methods: `__init__()`, `add_query(name, smarts)`, `remove_query(name)`, `query(mol, name) -> MatchResult`, `query_all(mol)`, `filter_molecules(molecules, query_name, mode)`, `from_query_dict(cls, queries)`, `get_query_names()`.
- **Function `query_functional_groups(mol) -> Dict[str, bool]` (line 457):** Tests 15 common functional groups (hydroxyl, amide, carboxylic acid, etc.).
- **Logic:** Substructure matching and molecular similarity toolkit. SMARTS/SMILES pattern matching, MCS search, Tanimoto/Dice similarity computation, pairwise similarity matrix, functional group querying, and batch molecule filtering.

---

## 39. `src/mbforge/molecules/models.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\molecules\models.py`
- **Lines:** 544
- **Imports:** Standard library: `logging`, `copy.deepcopy`, `dataclasses`, `pathlib.Path`, `typing`. Third-party: `rdkit.Chem`, `rdkit.Chem.Descriptors`
- **Module-level variables:** `logger`
- **Class `MoleculeEntry` (line 25, dataclass):** smiles, mol, name, activity, activity_unit, activity_raw, cas, cid, properties, tags, source, props.
  - `__post_init__`: Validates mol/smiles, auto-generates SMILES from mol or vice versa.
  - Factory methods: `from_smiles(cls, smiles, name, **kwargs)`, `from_mol(cls, mol, name, **kwargs)`, `from_dict(cls, data)` (backward-compatible with legacy dict format).
  - Utility methods: `to_dict()`, `copy()`, `has_activity()`, `num_atoms()`, `num_bonds()`, `molecular_weight()`, `logp()`, `__hash__` (by SMILES), `__eq__` (by SMILES).
- **Class `MoleculeBatch` (line 281):**
  - Sequence protocol: `__len__`, `__iter__`, `__getitem__`, `__contains__`.
  - Batch operations: `append`, `extend`, `deduplicate(key)` (SMILES dedup with activity averaging), `filter_by(predicate)`, `filter_has_activity()`, `filter_by_size(min_atoms, max_atoms)`, `sort_by(key, reverse)`, `sort_by_activity(reverse)`, `group_by(key)`, `get_activities()`.
  - Export: `to_dataframe()`, `to_dicts()`, `to_csv(path)`, `to_sdf(path)`, `to_excel(path)`.
- **Logic:** Typed molecule data models replacing raw dictionaries. `MoleculeEntry` ensures mol/smiles consistency with lazy conversion. `MoleculeBatch` provides a rich API for filtering, sorting, grouping, deduplication, and multi-format export.

---

## 40. `src/mbforge/molecules/standardizer.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\molecules\standardizer.py`
- **Lines:** 326
- **Imports:** Standard library: `logging`, `dataclasses`, `typing`. Third-party: `rdkit.Chem`, `rdkit.Chem.SaltRemover`, `rdkit.Chem.rdMolDescriptors`, `rdkit.Chem.MolStandardize.rdMolStandardize`
- **Module-level variables:** `logger`
- **Class `StandardizationResult` (line 31, dataclass):** mol, success, steps_applied, changes, errors.
- **Class `MoleculeStandardizer` (line 49):**
  - **Configurable steps:** remove_salts, remove_solvents, neutralize, tautomerize, clear_stereo, canonicalize_aromaticity, clear_atom_map_nums.
  - **Methods:**
    - `__init__(remove_salts, remove_solvents, neutralize, tautomerize, clear_stereo, canonicalize_aromaticity, clear_atom_map_nums)` (line 72)
    - `standardize(self, mol) -> StandardizationResult` (line 109): Full pipeline: salt removal -> solvent removal -> charge neutralization -> tautomer canonicalization -> RDKit normalize -> stereo cleanup -> aromaticity sanitize -> atom map num clearing. Tracks all applied steps and changes.
    - `standardize_smiles(self, smiles) -> Optional[str]` (line 205)
    - `standardize_batch(self, molecules, names) -> List[StandardizationResult]` (line 222)
    - `_remove_solvents(mol)` (static, line 246): Keeps largest non-solvent fragment (>3 heavy atoms).
    - `strip_salts(smiles)` (static, line 271)
    - `canonicalize_smiles(smiles)` (static, line 288)
    - `neutralize_smiles(smiles)` (static, line 308)
- **Logic:** Configurable molecule standardization pipeline using RDKit MolStandardize. Handles salt/solvent removal, charge neutralization, tautomer canonicalization, stereo cleanup, and aromaticity normalization. Reports all changes applied.

---

## 41. `src/mbforge/molecules/schema.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\molecules\schema.py`
- **Lines:** 228
- **Imports:** Standard library: `json`, `logging`, `uuid`, `dataclasses`, `pathlib.Path`, `typing`. Deferred: `rdkit.Chem`
- **Module-level variables:** `_RDKIT_AVAILABLE`, `logger`
- **Class `Molecule` (line 27, dataclass):** id, smiles, source, metadata, _rdkit_mol.
  - Property `rdkit_mol`: Lazy-loads from SMILES via `Chem.MolFromSmiles`.
  - Setter `rdkit_mol`: Sets mol and auto-updates SMILES.
  - `invalidate_rdk()`: Clears cache.
  - Factory: `from_smiles(cls, smiles, source, **metadata)`, `from_dict(cls, data)` (handles both schema and legacy reader formats).
  - Export: `to_dict()`, `to_json()`.
- **Class `MoleculeBatch` (line 134, dataclass):** molecules list.
  - Methods: `__len__`, `__iter__`, `filter_has_activity()`, `filter_by_smiles_length(max_len)`, `sort_by_activity(ascending)`, `to_dict_list()`.
  - Export: `to_csv(path)`, `to_sdf(path)`, `to_excel(path)`.
  - Factory: `from_smiles_list(cls, smiles_list, source)`.
- **Logic:** The canonical data contract for all algorithm modules (clustering, MCS, SAR). Stores only serializable fields; RDKit Mol is lazily reconstructed from SMILES. Backward-compatible with legacy reader dict format. Used as input/output format throughout the CSAR pipeline.

---

## 42. `src/mbforge/molecules/loader.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\molecules\loader.py`
- **Lines:** 135
- **Imports:** Standard library: `logging`, `pathlib.Path`, `typing`. Third-party: `rdkit.Chem`
- **Module-level variables:** `logger`
- **Functions:**
  - `load_molecules_from_file(path, smiles_column, activity_column, name_column) -> List[Dict]` (line 18): Dispatches by extension to `_load_sdf`, `_load_csv`, `_load_smiles_file`.
  - `_load_sdf(path) -> List[Dict]` (line 57): ForwardSDMolSupplier, extracts name/SMILES/all properties.
  - `_load_csv(path, smiles_column, activity_column, name_column) -> List[Dict]` (line 84): Pandas read_csv, SMILES validation.
  - `_load_smiles_file(path) -> List[Dict]` (line 116): Tab-separated SMILES files.
- **Logic:** Simple file loader for CLI tools. Loads SDF/CSV/SMI files into the legacy dict format with `mol` (RDKit) and `smiles` keys.

---

## 43. `src/mbforge/clustering/__init__.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\clustering\__init__.py`
- **Lines:** 32
- **Logic:** Exports `MolecularFingerprinter`, `MolecularClusterer`, `ClusteringError`, `ScaffoldClusterer`, `ScaffoldClusteringError`.

---

## 44. `src/mbforge/clustering/fingerprinter.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\clustering\fingerprinter.py`
- **Lines:** 206
- **Imports:** Standard library: `typing`, `dataclasses`. Third-party: `numpy`, `rdkit.Chem`, `rdkit.Chem.AllChem`, `rdkit.Chem.MACCSkeys`, `rdkit.DataStructs`
- **Class `FingerprintResult` (line 37, dataclass):** fingerprint (np.ndarray), fp_type, n_bits.
- **Class `MolecularFingerprinter` (line 53):**
  - Methods: `__init__(fp_type, radius, n_bits)`, `fingerprint(mol) -> FingerprintResult` (Morgan/MACCS/RDKit), `similarity(mol1, mol2) -> float`, `_tanimoto(fp1, fp2) -> float`, `pairwise_similarity(molecules) -> np.ndarray`.
- **Logic:** Molecular fingerprint calculator supporting Morgan (ECFP), MACCS, and RDKit topological fingerprints. Provides Tanimoto similarity computation and pairwise similarity matrix generation.

---

## 45. `src/mbforge/clustering/cluster.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\clustering\cluster.py`
- **Lines:** 288
- **Imports:** Standard library: `logging`, `typing`, `dataclasses`. Third-party: `numpy`, `rdkit.Chem`, `rdkit.ML.Cluster.Butina`. Internal: `.fingerprinter.MolecularFingerprinter`
- **Module-level variables:** `logger`
- **Class `ClusteringError(Exception)` (line 41)**
- **Class `ClusterResult` (line 50, dataclass):** cluster_id, molecules, representative_idx, size, avg_similarity.
- **Class `MolecularClusterer` (line 71):**
  - Methods: `__init__(fingerprinter, threshold, method)`, `cluster(molecules) -> Tuple[List[ClusterResult], np.ndarray]`, `_cluster_butina(molecules)` (distance matrix + Butina clustering), `_cluster_tanimoto(molecules)` (greedy threshold-based, defined after CLI block at line 235).
- **CLI entry** (line 196): Standalone clustering tool.
- **Logic:** Two clustering algorithms: Butina (distance-based, tighter clusters) and Tanimoto (greedy threshold). Both use molecular fingerprints. Returns cluster results with representative molecules and similarity matrix.

---

## 46. `src/mbforge/clustering/scaffold.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\clustering\scaffold.py`
- **Lines:** 351
- **Imports:** Standard library: `logging`, `typing`. Third-party: `rdkit.Chem`, `rdkit.Chem.Scaffolds.MurckoScaffold`
- **Module-level variables:** `logger`
- **Class `ScaffoldClusteringError(Exception)` (line 40)**
- **Function `get_murcko_scaffold(mol, include_chirality) -> Optional[Mol]` (line 46)**
- **Function `get_murcko_scaffold_smiles(mol, include_chirality) -> str` (line 80)**
- **Class `ScaffoldClusterResult` (line 99):** scaffold_smiles, scaffold_mol, molecules, num_molecules, activities, mean/min/max_activity.
- **Class `ScaffoldClusterer` (line 150):**
  - Methods: `__init__(include_chirality, merge_aromatic_kekulize, min_cluster_size)`, `_normalize_scaffold_smiles(smiles)`, `cluster(molecules) -> List[ScaffoldClusterResult]`, `get_scaffold_diversity(molecules) -> Dict` (unique scaffolds, singletons, diversity index).
- **CLI entry** (line 311): Standalone scaffold clustering tool.
- **Logic:** Bemis-Murcko scaffold-based clustering. Groups molecules by their Murcko scaffold SMILES. Supports chirality control and aromatic/Kekule form merging. Computes scaffold diversity metrics.

---

## 47. `src/mbforge/sar/__init__.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\sar\__init__.py`
- **Lines:** 40
- **Logic:** Exports `ActivityPreprocessor`, `CensoredType`, `SARAnalyzer`, `SARError`, `SARResult`.

---

## 48. `src/mbforge/sar/analyzer.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\sar\analyzer.py`
- **Lines:** 367
- **Imports:** Standard library: `logging`, `typing`, `dataclasses`, `collections.defaultdict`. Third-party: `numpy`, `rdkit.Chem`, `rdkit.Chem.AllChem`, `rdkit.Chem.Descriptors`. Internal: `..mcs.finder.MCSResult`
- **Module-level variables:** `logger`
- **Class `SARError(Exception)` (line 42)**
- **Class `SARResult` (line 51, dataclass):** cluster_id, mcs, activities, mean/std/max/min_activity, num_compounds, contributions.
- **Class `SARAnalyzer` (line 80):**
  - Methods: `__init__(activity_threshold, use_mcs)`, `analyze_cluster(cluster_id, molecules, mcs_result) -> SARResult`, `_analyze_contributions(molecules, mcs_result) -> Dict[str, float]` (identifies side chains on MCS, averages activity per substituent type), `_get_side_chains(mol, mcs_mol) -> Dict[int, List[int]]`, `analyze_clusters(clusters, mcs_results) -> Dict[int, SARResult]`, `get_activity_stats(sar_results) -> Dict[str, float]` (cross-cluster aggregation).
- **CLI entry** (line 321): Standalone SAR analysis tool.
- **Logic:** SAR analysis engine. For each cluster, computes activity statistics (mean, std, min, max), analyzes substructure contributions by identifying side chains on MCS scaffolds and correlating substituent types with activity levels.

---

## 49. `src/mbforge/sar/preprocessor.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\sar\preprocessor.py`
- **Lines:** 517
- **Imports:** Standard library: `logging`, `re`, `dataclasses`, `enum`, `typing`. Third-party: `numpy`. Internal: `..mcs.finder.MCSResult` (imported but unused)
- **Module-level variables:** `UNIT_TO_NM` (dict), `logger`
- **Enum `ActivityUnit` (line 38):** NM, UM, MM, UNKNOWN.
- **Enum `CensoredType` (line 55):** NONE, GREATER_THAN, LESS_THAN, TILDE.
- **Class `CensoredValue` (line 63, dataclass):** value, censored_type, raw_string.
- **Class `ProcessedActivity` (line 77, dataclass):** raw, value_nm, p_value, censored, is_outlier, unit.
- **Class `DataQualityReport` (line 98, dataclass):** total_molecules, valid/invalid_activities, censored_values, outliers, unit_counts, activity/p_activity_range, failed_molecules. Method: `summary() -> str`.
- **Class `ActivityPreprocessor` (line 153):**
  - **Class variables:** `_UNIT_PATTERNS` (regex for nM/uM/mM), `_CENSORED_PATTERNS` (regex for >, <, ~, approx).
  - **Methods:**
    - `__init__(iqr_multiplier, enable_p_conversion, enable_outlier_detection, censor_treatment)` (line 192)
    - `detect_unit(raw_value) -> ActivityUnit` (line 217)
    - `parse_censored(raw_value) -> Optional[CensoredValue]` (line 233)
    - `clean_numeric(raw_value) -> Tuple[Optional[float], ActivityUnit, Optional[CensoredValue]]` (line 252): Extracts numeric value, unit, and censored info from mixed string.
    - `convert_to_nm(value, unit) -> float` (line 306)
    - `to_p_activity(value_nm) -> float` (line 318): pIC50 = 9 - log10(IC50_nM).
    - `detect_outliers_iqr(values) -> List[bool]` (line 333): Tukey's fences.
    - `process_molecule(mol_data) -> Optional[Dict]` (line 357): Processes single molecule's activity.
    - `process(molecules, activity_key, raw_key) -> List[Dict]` (line 414): Full pipeline: parse -> normalize to nM -> pActivity -> outlier detection -> quality report.
    - `get_quality_report() -> DataQualityReport` (line 510)
- **Logic:** Activity data preprocessing pipeline. Handles unit detection/conversion (nM/uM/mM -> nM), censored data parsing (>, <, ~), pActivity computation, IQR-based outlier detection, and generates data quality reports.

---

## 50. `src/mbforge/parsers/__init__.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\parsers\__init__.py`
- **Lines:** 30
- **Logic:** Exports `process_file`, `get_strategy`, all strategy classes, `PDFParserPipeline`, `MoleculeExtractor`.

---

## 51. `src/mbforge/parsers/file_processor.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\parsers\file_processor.py`
- **Lines:** 371
- **Imports:** Standard library: `json`, `shutil`, `abc`, `pathlib.Path`, `typing`. Internal: `..core.document.ExtractedContent`, `..core.todo_manager.TodoEntry`, `..utils.helpers.split_text_chunks`, `..utils.logger.get_logger`
- **Module-level variables:** `STRATEGIES` (dict mapping extensions to strategy instances), `logger`
- **Class `FileProcessStrategy` (line 27, ABC):** Abstract with `extract(entry, source, output_dir) -> ExtractedContent`, `index(content, entry, **deps)`, `store(content, entry, output_dir) -> Dict`.
- **Concrete strategies:**
  - `PDFStrategy` (line 66): Uses `PDFParserPipeline`, indexes to KB + mol_db, stores summary + molecules.
  - `MarkdownStrategy` (line 123): Reads text, chunks, base index/store.
  - `TextStrategy` (line 138): Same as Markdown but with `errors='replace'`.
  - `MoleculeStrategy` (line 153): Parses SDF/MOL/PDB/SMI via RDKit, indexes molecules to mol_db + text to RAG.
  - `DataTableStrategy` (line 230): Pandas CSV/XLSX -> text representation + structured data.json.
  - `JsonStrategy` (line 282): Reads JSON, truncates at 20K chars, chunks.
- **Function `get_strategy(ext) -> FileProcessStrategy` (line 320)**
- **Function `process_file(entry, source_path, output_dir, llm, embedder, vlm, knowledge_base, mol_db) -> Dict` (line 327):** Unified entry point: extract -> index -> store. Returns result dict with metadata.
- **Logic:** Strategy pattern for file processing. Each file type has a dedicated strategy that handles extraction, RAG indexing, and output storage. The `process_file` function orchestrates the pipeline for any supported file type.

---

## 52. `src/mbforge/parsers/glm_ocr_parser.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\parsers\glm_ocr_parser.py`
- **Lines:** 226
- **Imports:** Standard library: `base64`, `io`, `json`, `pathlib.Path`, `typing`. Third-party: `requests`. Internal: `..utils.logger.get_logger`
- **Module-level variables:** `logger`
- **Class `GlmOcrClient` (line 27):**
  - Methods: `__init__(provider, base_url, api_key, model_name, timeout)`, `_encode_image(image_path) -> str`, `_call_api(image_b64, prompt) -> str` (OpenAI-compatible vision API), `parse_pdf(pdf_path) -> Dict` (with PyMuPDF fallback), `_parse_with_glm(pdf_path)` (page-by-page OCR), `_fallback_pymupdf(pdf_path)`, `_pdf_to_images(pdf_path, dpi)`, `_extract_molecule_placeholders(markdown, page_idx)`, `_markdown_to_text(markdown)`.
- **Logic:** GLM-OCR client for PDF parsing via vision LLM. Converts PDF pages to images, sends to OpenAI-compatible API with chemistry-specific OCR prompt, extracts molecule image placeholders from markdown output. Falls back to PyMuPDF on failure.

---

## 53. `src/mbforge/parsers/pdf_parser.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\parsers\pdf_parser.py`
- **Lines:** 151
- **Imports:** Standard library: `tempfile`, `concurrent.futures`, `pathlib.Path`, `typing`. Internal: `..core.document.DocumentProcessor`, `..core.document.ExtractedContent`, `..core.knowledge_base.KnowledgeBase`, `..core.mol_database.MoleculeDatabase`, `..core.mol_database.MoleculeRecord`, `..parsers.molecule_extractor.MoleculeExtractor`, `..utils.helpers.generate_uuid`, `..utils.logger.get_logger`. Deferred: `..utils.helpers.split_text_chunks`, `..core.summarizer.DocumentSummarizer`, `..core.summarizer.SummaryManager`, `..models.base.Message`
- **Module-level variables:** `logger`
- **Class `PDFParserPipeline` (line 23):**
  - Methods:
    - `__init__(llm, embedder, vlm, knowledge_base, mol_db)` (line 35)
    - `parse(pdf_path, doc_id, extract_molecules, summarize, index_kb) -> ExtractedContent` (line 50): Full pipeline: (1) PyMuPDF text extraction, (2) image extraction, (3) VLM analysis of images (parallel ThreadPoolExecutor, max 5 images), (4) LLM summary + L0/L1/L2 via DocumentSummarizer, (5) molecule extraction via MoleculeExtractor, (6) KB indexing.
    - `_summarize(text) -> str` (line 126): Direct LLM summary (not used in main pipeline).
    - `_extract_molecules(text, doc_id) -> List[MoleculeRecord]` (line 145): Extracts molecules and adds to mol_db.
- **Logic:** End-to-end PDF processing pipeline. Extracts text and images via PyMuPDF, analyzes images with VLM (parallel), generates multi-level summaries via LLM, extracts molecules from text, and indexes everything to the knowledge base and molecule database.

---

## 54. `src/mbforge/parsers/molecule_extractor.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\parsers\molecule_extractor.py`
- **Lines:** 139
- **Imports:** Standard library: `re`, `typing`. Deferred: `rdkit.Chem`. Internal: `..molecules.schema.Molecule`
- **Module-level variables:** None (class-level regex patterns)
- **Class `MoleculeExtractor` (line 19):**
  - **Class variables:** `SMILES_PATTERN` (regex for SMILES-like strings), `ACTIVITY_PATTERN` (regex for IC50/EC50/Ki/Kd with value and unit).
  - **Methods:**
    - `__init__(self)` (line 33): Initializes `_seen_smiles` set.
    - `is_valid_smiles(self, smiles) -> bool` (line 36): RDKit validation or basic syntax fallback.
    - `extract_smiles_candidates(self, text) -> List[str]` (line 47): Regex scan + validation + dedup.
    - `extract_activities(self, text) -> List[Dict]` (line 59): Regex extraction of activity data with context.
    - `extract_from_text(self, text, doc_id) -> List[Molecule]` (line 71): Matches SMILES to nearest activity data (within 200 chars), creates `Molecule` objects.
    - `extract_from_pdf_result(self, result_dict, doc_id) -> List[Molecule]` (line 117): Extracts from UniParser-style structured results.
- **Logic:** Regex-based molecule extraction from unstructured text. Identifies SMILES strings, validates them via RDKit, extracts activity data (IC50/EC50/Ki/Kd), and matches molecules to their nearest activity measurements by text proximity.

---

## 55. `src/mbforge/parsers/local/__init__.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\parsers\local\__init__.py`
- **Lines:** 26
- **Logic:** Re-exports `MoleculeExtractor` from parent module. Local PDF processing track (parallel to parsers/uniparser/ UniParser API track).

---

## 60. `src/mbforge/utils/__init__.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\utils\__init__.py`
- **Lines:** 32
- **Logic:** Exports all utility functions and config classes.

---

## 61. `src/mbforge/utils/config.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\utils\config.py`
- **Lines:** 207
- **Imports:** Standard library: `json`, `os`, `dataclasses`, `typing`. Internal: `..utils.constants.*` (GLOBAL_CONFIG_DIR, provider strings, default models, OCR provider, HF_ENDPOINT)
- **Module-level variables:** `_CONFIG_PATH`, `_config_cache`
- **Dataclasses:**
  - `ModelConfig` (line 23): provider, base_url, api_key, model_name, max_tokens, temperature, top_p.
  - `EmbedConfig` (line 36): provider, model_name, base_url, api_key, device, mrl_dim, instruction.
  - `RerankConfig` (line 49): provider, model_name, device, max_length.
  - `VLMConfig` (line 59): provider, base_url, api_key, model_name.
  - `OcrConfig` (line 69): provider, base_url, api_key, model_name, use_hf_mirror.
  - `AppConfig` (line 80): llm, embed, rerank, vlm, ocr, recent_projects, theme, language. Methods: `to_dict()`, `from_dict(cls, data)`.
- **Functions:**
  - `_config_from_env() -> AppConfig` (line 113): Builds config from `MBFORGE_*` env vars.
  - `load_global_config() -> AppConfig` (line 156): Priority: memory cache -> config file -> env vars -> defaults.
  - `save_global_config(config)` (line 184)
  - `get_env_or_config(key, default) -> str` (line 193)
  - `setup_hf_mirror()` (line 198): Sets `HF_ENDPOINT` for Chinese mirror.
- **Logic:** Global application configuration. Nested dataclass hierarchy for LLM/Embed/Rerank/VLM/OCR settings. Persisted to `~/.config/MBForge/config.json` with env var fallback. Supports HuggingFace mirror setup for China.

---

## 62. `src/mbforge/utils/helpers.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\utils\helpers.py`
- **Lines:** 118
- **Imports:** Standard library: `asyncio`, `hashlib`, `json`, `re`, `uuid`, `pathlib.Path`, `typing`
- **Functions:**
  - `generate_uuid() -> str` (line 14)
  - `sha256_file(path) -> str` (line 19)
  - `sha256_text(text) -> str` (line 28)
  - `safe_filename(name) -> str` (line 33)
  - `truncate_text(text, max_len) -> str` (line 38)
  - `split_text_chunks(text, chunk_size, overlap) -> List[str]` (line 45): Splits at paragraph/sentence/word boundaries with overlap.
  - `format_molecule_info(smiles, name, activity) -> str` (line 75)
  - `ensure_dir(path)` (line 85)
  - `save_json(path, data)` (line 90)
  - `load_json(path, default)` (line 97)
  - `run_sync(sync_func, *args)` (line 106): Runs sync function in thread pool if inside async loop.
- **Logic:** General-purpose utility functions: UUID generation, SHA256 hashing, text chunking (boundary-aware with overlap), JSON I/O, filename sanitization, and async compatibility.

---

## 63. `src/mbforge/utils/logger.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\utils\logger.py`
- **Lines:** 93
- **Imports:** Standard library: `logging`, `sys`, `pathlib.Path`, `typing`. Internal: `..utils.constants.APP_NAME`, `..utils.constants.GLOBAL_DATA_DIR`
- **Module-level variables:** `_CONSOLE_FORMAT`, `_FILE_FORMAT`, `_DATE_FORMAT`, `_logger_initialized`
- **Functions:**
  - `setup_logging(level, log_dir, console, file)` (line 29): Configures root logger with console + rotating file handler (10MB, 5 backups).
  - `get_logger(name) -> logging.Logger` (line 85): Auto-initializes if needed.
- **Logic:** Logging setup with both console and file output. File logs go to `~/.local/share/MBForge/logs/mbforge.log` with rotation.

---

## 64. `src/mbforge/utils/error_logger.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\utils\error_logger.py`
- **Lines:** 122
- **Imports:** Standard library: `traceback`, `datetime`, `pathlib.Path`, `typing`. Internal: `..utils.logger.get_logger`
- **Module-level variables:** `_ERRORS_DIR` (points to `docs/errors/`)
- **Functions:**
  - `record_error(module, summary, error, solution, status) -> Path` (line 22): Creates dated markdown file with error details, stack trace, and solution. Updates README.md index table.
  - `_update_index(date_str, num_str, module, summary, status)` (line 92): Inserts row into errors/README.md table.
- **Logic:** Error documentation system. Records runtime errors as individual markdown files in `docs/errors/` with full stack traces, and maintains a README.md index table.

---

## 65. `src/mbforge/utils/constants.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\utils\constants.py`
- **Lines:** 96
- **Imports:** `pathlib.Path`, `platformdirs.user_data_dir`, `platformdirs.user_config_dir`
- **Module-level variables:** APP_NAME, APP_AUTHOR, APP_VERSION ("0.2.0"), PROJECT_META_DIR (".mbforge"), GLOBAL_CONFIG_DIR, GLOBAL_DATA_DIR, DEFAULT_EMBED_MODEL ("Qwen/Qwen3-Embedding-0.6B"), DEFAULT_RERANK_MODEL ("Qwen/Qwen3-Reranker-0.6B"), DEFAULT_LLM_MODEL, DEFAULT_VLM_MODEL, DEFAULT_HF_ENDPOINT, EMBED_INSTRUCTION_RETRIEVAL/CLUSTER, RERANK_DEFAULT_INSTRUCTION, SUPPORTED_DOC_EXTS, SUPPORTED_MOL_EXTS, KB_COLLECTION_DOCS/MOLECULES, PDF_CHUNK_SIZE/OVERLAP, LLM_MAX_TOKENS/TEMPERATURE/TOP_P, MOL_DB_FILENAME, MEMORY_DIR, TRAJECTORY_DIR/FILE, SUMMARY_DIR, TODO_FILE, OUTPUT_DIR, SETTINGS_FILE, INDEX_FILE, PROVIDER_* strings, OCR_PROVIDER_* strings, VIKING_SCHEME, META_* keys.
- **Logic:** Central constants definition. All path templates, default model names, provider identifiers, supported file extensions, and metadata key names.

---

## 66. `src/mbforge/models/__init__.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\models\__init__.py`
- **Lines:** 28
- **Logic:** Exports all model interfaces and factory functions.

---

## 67. `src/mbforge/models/base.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\models\base.py`
- **Lines:** 88
- **Imports:** Standard library: `abc`, `dataclasses`, `typing`
- **Class `Message` (line 11, dataclass):** role, content, attachments, tool_call_id, name, tool_calls.
- **Class `StreamChunk` (line 23, dataclass):** delta, finish_reason.
- **Class `BaseLLM` (line 30, ABC):** Abstract methods: `chat`, `chat_stream`, `achat`, `achat_stream`.
- **Class `BaseEmbedder` (line 54, ABC):** Abstract methods: `embed`, `aembed`.
- **Class `BaseReranker` (line 68, ABC):** Abstract method: `rerank`.
- **Class `BaseVLM` (line 77, ABC):** Abstract methods: `describe_image`, `describe_pdf_page`.
- **Logic:** Abstract base classes defining the unified interface for all AI model backends (LLM, Embedder, Reranker, VLM) with both sync and async variants.

---

## 68. `src/mbforge/models/vlm.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\models\vlm.py`
- **Lines:** 62
- **Imports:** Standard library: `base64`, `pathlib.Path`. Third-party: `openai`. Internal: `.base.BaseVLM`
- **Class `APIVLM(BaseVLM)` (line 13):** OpenAI-compatible vision LLM.
  - Methods: `__init__(base_url, api_key, model_name)`, `_encode_image(image_path) -> str`, `describe_image(image_path, prompt) -> str`, `describe_pdf_page(image_path, context) -> str`.
- **Function `create_vlm_from_config(config)` (line 57)**
- **Logic:** Vision LLM via OpenAI-compatible API. Base64-encodes images, sends with text prompt, returns description. Used for PDF page analysis.

---

## 69. `src/mbforge/models/llm.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\models\llm.py`
- **Lines:** 118
- **Imports:** Standard library: `typing`. Third-party: `openai`. Internal: `.base.BaseLLM`, `.base.Message`, `.base.StreamChunk`
- **Class `OpenAILLM(BaseLLM)` (line 12):** OpenAI-compatible LLM.
  - Methods: `__init__(base_url, api_key, model_name, max_tokens, temperature, top_p)`, `_convert_messages(messages)`, `chat(messages) -> str`, `chat_stream(messages) -> Iterator[StreamChunk]`, `achat(messages) -> str`, `achat_stream(messages) -> AsyncGenerator`.
- **Function `create_llm_from_config(config) -> BaseLLM` (line 82):** Dispatches by provider to `NemotronDiffusionLLM`, `AnthropicLLM`, or `OpenAILLM`.
- **Logic:** OpenAI-compatible LLM implementation using the openai SDK. Supports sync/async chat and streaming. Factory function routes to correct implementation based on provider config.

---

## 70. `src/mbforge/models/anthropic_llm.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\models\anthropic_llm.py`
- **Lines:** 208
- **Imports:** Standard library: `typing`. Third-party: `anthropic` (deferred). Internal: `.base.BaseLLM`, `.base.Message`, `.base.StreamChunk`
- **Class `AnthropicLLM(BaseLLM)` (line 10):** Anthropic-compatible LLM (MiniMax).
  - Methods:
    - `__init__(base_url, api_key, model_name, max_tokens, temperature, top_p)` (line 17)
    - `_convert_messages(messages) -> Tuple[str, List[dict]]` (line 44): Converts MBForge Messages to Anthropic format (system text extraction, tool_result blocks, tool_use blocks).
    - `_convert_tools(openai_tools) -> List[dict]` (line 91): OpenAI tools -> Anthropic tools format.
    - `_build_params(messages, **kwargs) -> Dict` (line 103)
    - `chat(messages) -> str` (line 126)
    - `chat_stream(messages) -> Iterator[StreamChunk]` (line 131): Handles text_delta and thinking_delta.
    - `achat(messages)`, `achat_stream(messages)`
    - `call_with_tools(messages, tools, tool_choice, **kwargs)` (line 162): Function calling with Anthropic API.
    - `call_with_tools_stream(messages, tools, tool_choice, **kwargs)` (line 181)
    - `_extract_text(response) -> str` (static, line 200)
- **Logic:** Anthropic SDK implementation for MiniMax and other Anthropic-compatible APIs. Full message format conversion (system/tool_result/tool_use blocks), tool calling support, streaming with thinking delta handling, max_tokens capped at 196608.

---

## 71. `src/mbforge/models/rerank.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\models\rerank.py`
- **Lines:** 58
- **Imports:** Standard library: `typing`. Internal: `.base.BaseReranker`, `..utils.constants.PROVIDER_SENTENCE_TRANSFORMERS`, `..utils.constants.PROVIDER_QWEN3`, `..utils.logger.get_logger`
- **Module-level variables:** `logger`
- **Class `SentenceTransformerReranker(BaseReranker)` (line 14):** CrossEncoder-based reranker.
  - Methods: `__init__(model_name, device)`, `_load_model()`, `rerank(query, passages) -> List[tuple[int, float]]`.
- **Function `create_reranker_from_config(config) -> BaseReranker` (line 40):** Routes to `Qwen3Reranker` or `SentenceTransformerReranker`.
- **Logic:** Reranker factory. Default uses Qwen3 generative reranker; falls back to sentence-transformers CrossEncoder.

---

## 72. `src/mbforge/models/embedding.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\models\embedding.py`
- **Lines:** 235
- **Imports:** Standard library: `os`, `typing`, `pathlib.Path`. Third-party: `openai`. Internal: `.base.BaseEmbedder`, `..utils.constants.*`, `..utils.logger.get_logger`
- **Module-level variables:** `logger`
- **Functions:** `_ensure_hf_mirror()`, `_resolve_model_path(model_name, cache_name) -> str` (searches ModelScope cache).
- **Class `SentenceTransformerEmbedder(BaseEmbedder)` (line 77):** Generic sentence-transformers embedder.
  - Methods: `__init__(model_name, device)`, `_load_model()`, `dim` (property), `embed(texts) -> List[List[float]]`, `aembed(texts)`.
- **Class `Qwen3Embedder(BaseEmbedder)` (line 114):** Qwen3-Embedding with Instruction Aware and MRL support.
  - Class variables: `INSTRUCTION_RETRIEVAL`, `INSTRUCTION_CLUSTER`, `INSTRUCTION_CLASSIFICATION`.
  - Methods: `__init__(model_name, device, mrl_dim, instruction)`, `_load_model()`, `dim` (property), `embed(texts)` (prepends instruction, applies MRL truncation), `aembed(texts)`.
- **Class `APIEmbedder(BaseEmbedder)` (line 193):** OpenAI-compatible API embedder.
  - Methods: `__init__(base_url, api_key, model_name)`, `embed(texts)`, `aembed(texts)`.
- **Function `create_embedder_from_config(config) -> BaseEmbedder` (line 213):** Routes by provider.
- **Logic:** Three embedder implementations. Qwen3Embedder is the default with instruction-aware encoding and MRL dimension reduction. ModelScope cache resolution for offline model loading. HF mirror setup for China.

---

## 73. `src/mbforge/models/rerank_qwen3.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\models\rerank_qwen3.py`
- **Lines:** 212
- **Imports:** Standard library: `os`, `typing`, `pathlib.Path`. Third-party: `torch`, `transformers.AutoTokenizer`, `transformers.AutoModelForCausalLM`. Internal: `.base.BaseReranker`, `..utils.constants.DEFAULT_RERANK_MODEL`, `..utils.constants.DEFAULT_HF_ENDPOINT`, `..utils.logger.get_logger`
- **Module-level variables:** `logger`
- **Functions:** `_ensure_hf_mirror()`, `_resolve_rerank_model_path(model_name) -> str`.
- **Class `Qwen3Reranker(BaseReranker)` (line 71):**
  - **Class variables:** `DEFAULT_INSTRUCTION`, `_PREFIX`, `_SUFFIX` (ChatML prompt template with thinking tags).
  - **Methods:**
    - `__init__(model_name, device, max_length, instruction)` (line 93)
    - `_load()` (line 111): Lazy-loads tokenizer + model, pre-encodes prefix/suffix tokens, resolves yes/no token IDs.
    - `_format_pair(query, doc, instruction) -> str` (line 143)
    - `rerank(query, passages) -> List[tuple[int, float]]` (line 148): Tokenizes pairs, wraps with prefix+suffix, runs forward pass, extracts yes-token logits, applies log_softmax, returns sorted by probability.
- **Logic:** Qwen3-Reranker implementation. Uses CausalLM architecture (not CrossEncoder) with yes/no probability scoring. Constructs ChatML-format prompts with instruction/query/document, takes the last token's yes/no logits, and normalizes to probability scores. Supports MRL and ModelScope cache.

---

## 74. `src/mbforge/models/nemotron_diffusion.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\models\nemotron_diffusion.py`
- **Lines:** 137
- **Imports:** Standard library: `os`, `typing`. Third-party: `torch`. Internal: `.base.BaseLLM`, `.base.Message`, `.base.StreamChunk`, `..utils.logger.get_logger`. Deferred: `modelscope.AutoModel`, `modelscope.AutoTokenizer`, `.embedding._resolve_model_path`
- **Module-level variables:** `logger`
- **Function `_ensure_hf_mirror()` (line 27)**
- **Class `NemotronDiffusionLLM(BaseLLM)` (line 32):**
  - **Methods:**
    - `__init__(model_path, device, dtype, max_new_tokens, mode)` (line 38): mode = "ar" | "dlm" | "linear_spec".
    - `_resolve_dtype() -> torch.dtype` (line 54)
    - `_load()` (line 61): Loads via ModelScope AutoModel/AutoTokenizer.
    - `_generate(messages) -> str` (line 83): Applies chat template, dispatches to `model.generate` (AR), `model.generate` (DLM with block_length=32, threshold=0.9), or `model.linear_spec_generate` (linear self-speculation).
    - `chat(messages) -> str` (line 122)
    - `chat_stream(messages) -> Iterator[StreamChunk]` (line 125): Non-streaming yield (full result at once).
    - `achat(messages)`, `achat_stream(messages)`
- **Logic:** Nemotron-Labs-Diffusion-3B local inference. Supports three generation modes: autoregressive (AR), diffusion language model (dLM) with block-parallel generation, and linear self-speculation acceleration. Uses ModelScope for model loading. Stream is simulated (full generation then single chunk yield).

---

## 75. `src/mbforge/ui/__init__.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\ui\__init__.py`
- **Lines:** 14
- **Logic:** Exports `MainWindow`, `ChatWidget`, `NewProjectDialog`, `SettingsDialog`, `MoleculeInfoDialog`.

---

## 76. `src/mbforge/ui/main_window.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\ui\main_window.py`
- **Lines:** 1008
- **Imports:** Standard library: `pathlib.Path`, `typing`. PyQt6: extensive widget imports. Internal: agent, core, models, parsers, utils, and all UI modules.
- **Class `IndexWorker(QThread)` (line 49):** Background PDF indexing thread.
  - Signals: `progress(str)`, `finished_signal()`.
  - Methods: `__init__(pipeline, entries)`, `run()`.
- **Class `MainWindow(QMainWindow)` (line 79):**
  - **Attributes:** project, kb, mol_db, todo_manager, llm, embedder, reranker, vlm, pdf_pipeline, agent.
  - **Methods (40+):**
    - `_setup_models()` (line 109): Initializes embedder, LLM, reranker from config.
    - `_setup_ui()` (line 127): Three-panel layout: left (file tree + scan/index buttons), center (tabbed workspace), right (KB search + chat). Splitter-based.
    - `_setup_menubar()` (line 303): File (new/open/import/process/save/exit), Edit (settings), View (toggle chat), Tools (index/mol_db).
    - `_setup_toolbar()` (line 374): Quick actions toolbar.
    - `_setup_statusbar()` (line 413): Status bar with progress bar.
    - `_apply_theme()` (line 432): Comprehensive white/clean Qt stylesheet.
    - `_new_project()` (line 581): NewProjectDialog -> Project.create -> _load_project.
    - `_open_project()` (line 597): Folder dialog -> Project.open -> _load_project.
    - `_open_recent_project()` (line 615): Auto-opens most recent valid project on startup.
    - `_load_project(project)` (line 634): Releases old resources, initializes KB/mol_db/todo_manager/pdf_pipeline/agent, restores conversation memory, refreshes file tree.
    - `_scan_project()` (line 698)
    - `_index_project()` (line 705): Launches IndexWorker for all unindexed files.
    - `_index_single_file(path)` (line 721)
    - `_on_index_finished()` (line 732)
    - `_open_file(path)` (line 739): Dispatches by extension to PDFViewer or text editor+preview.
    - `_open_text_file(path)` (line 760): Split view with MarkdownEditor + MarkdownPreview.
    - `_open_external_file()` (line 788)
    - `_import_files()` (line 798): Copies files to raw/, adds to TODO queue, auto-processes if enabled.
    - `_close_tab(index)` (line 845)
    - `_should_auto_process()` (line 853)
    - `_start_process_todo()` (line 859): Launches async TODO processing with progress bar, runs archive agent on completion.
    - `_run_archive_agent()` (line 898)
    - `_save_current()` (line 910)
    - `_search_kb()` (line 926): Hybrid search + rerank, displays results, injects into chat context.
    - `_show_settings()` (line 955)
    - `_toggle_chat_panel()` (line 968)
    - `_show_mol_db()` (line 971): Opens MoleculePanel tab.
    - `closeEvent(event)` (line 980): Saves conversation memory, extracts structured memory, releases resources.
- **Logic:** The main application window. Three-panel layout with file tree, tabbed workspace (PDF viewer, markdown editor+preview, molecule database), and AI chat panel. Orchestrates project lifecycle, file import/processing, knowledge base search, and AI agent interaction. Full keyboard shortcuts, progress tracking, and clean white theme.

---

## 77. `src/mbforge/ui/chat_widget.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\ui\chat_widget.py`
- **Lines:** 291
- **Imports:** Standard library: `typing`. PyQt6: extensive widget imports. Internal: `..agent.agent.ProjectAgent`, `..utils.logger.get_logger`
- **Module-level variables:** `logger`
- **Class `ChatMessage(QWidget)` (line 27):** Single message bubble with header and body.
- **Class `StreamWorker(QThread)` (line 60):** Background thread for LLM streaming.
  - Signals: `chunk_received(str)`, `finished_signal()`, `error_signal(str)`.
  - Methods: `__init__(agent, user_input)`, `run()` (calls `agent.chat_stream`), `stop()`.
- **Class `ChatWidget(QWidget)` (line 88):**
  - Methods:
    - `__init__(parent)` (line 91)
    - `_setup_ui()` (line 98): Toolbar (title + clear button), scrollable messages area, input box + send/stop buttons.
    - `set_agent(agent)` (line 201)
    - `set_system_prompt(prompt)` (line 205)
    - `add_context(context)` (line 210): Injects KB search results into agent context.
    - `_send_message()` (line 216): Creates user message, spawns StreamWorker, shows stop button.
    - `_on_chunk(text)` (line 247): Appends streamed text to current reply widget.
    - `_on_stream_finished()` (line 256)
    - `_on_stream_error(error)` (line 262)
    - `_stop_generation()` (line 267)
    - `_add_message(role, content)` (line 274)
    - `_scroll_to_bottom()` (line 279)
    - `clear_chat()` (line 284)
- **Logic:** Chat UI component with streaming support. User types message, StreamWorker runs agent.chat_stream in background thread, chunks are emitted via Qt signals and appended to the reply bubble in real-time. Supports stop button and context injection from KB search.

---

## 78. `src/mbforge/ui/dialogs.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\ui\dialogs.py`
- **Lines:** 365
- **Imports:** Standard library: `pathlib.Path`, `typing`. PyQt6: extensive dialog/widget imports. Internal: `..utils.config.AppConfig`, `..utils.config.ModelConfig`, `..utils.config.EmbedConfig`, `..utils.config.RerankConfig`, `..utils.config.VLMConfig`
- **Class `NewProjectDialog(QDialog)` (line 30):** Name, path (with browse), description fields. Method: `get_data() -> dict`.
- **Class `SettingsDialog(QDialog)` (line 120):** Tabbed settings for LLM, Embedding, Rerank, VLM. Loads/saves `AppConfig`.
  - Methods: `_setup_ui()`, `_setup_llm_tab()` (provider combo, base_url, api_key, model, max_tokens, temperature), `_setup_embed_tab()` (provider, model, device), `_setup_rerank_tab()`, `_setup_vlm_tab()`, `_load_config()`, `_save_and_accept()`.
- **Class `MoleculeInfoDialog(QDialog)` (line 320):** Shows molecule structure image (via `MoleculeImageWidget`) + detailed info (SMILES, name, activity, source, properties, tags, notes).
- **Logic:** Application dialogs. New project creation, global settings management (4 model tabs), and molecule detail viewer with rendered structure image.

---

## 79. `src/mbforge/ui/editor.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\ui\editor.py`
- **Lines:** 79
- **Imports:** Standard library: `pathlib.Path`, `typing`. PyQt6: `pyqtSignal`, `QFont`, `QPlainTextEdit`, `QWidget`
- **Class `MarkdownEditor(QPlainTextEdit)` (line 16):**
  - Signals: `content_changed`
  - Methods: `__init__(parent)`, `_on_text_changed()`, `load_file(path)`, `save_file() -> bool`, `is_modified() -> bool`, `insert_text(text)`.
- **Logic:** Simple monospace text editor with file load/save and modification tracking. Consolas font, clean styling.

---

## 80. `src/mbforge/ui/file_tree.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\ui\file_tree.py`
- **Lines:** 132
- **Imports:** Standard library: `pathlib.Path`, `typing`. PyQt6: `pyqtSignal`, `QMenu`, `QTreeWidget`, `QTreeWidgetItem`, `QWidget`. Internal: `..core.project.Project`, `..utils.constants.PROJECT_META_DIR`, `..utils.constants.SUPPORTED_DOC_EXTS`, `..utils.constants.SUPPORTED_MOL_EXTS`
- **Class `FileTreeWidget(QTreeWidget)` (line 20):**
  - Signals: `file_selected(Path)`, `file_opened(Path)`.
  - Methods: `__init__(parent)`, `set_project(project)`, `refresh()`, `_populate_tree(dir_path, parent_item)` (recursive, skips hidden/.mbforge), `_on_double_click(item, column)`, `_show_context_menu(position)` (open/refresh/index actions), `get_selected_path() -> Optional[Path]`.
- **Logic:** Project file tree widget. Recursively displays project directory structure, filters by supported extensions, provides context menu with open/refresh/index actions.

---

## 81. `src/mbforge/ui/mol_panel.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\ui\mol_panel.py`
- **Lines:** 113
- **Imports:** Standard library: `typing`. PyQt6: widget imports. Internal: `..core.mol_database.MoleculeDatabase`, `..core.mol_database.MoleculeRecord`, `.dialogs.MoleculeInfoDialog`
- **Class `MoleculePanel(QWidget)` (line 21):**
  - Signals: `molecule_selected(MoleculeRecord)`.
  - Methods: `__init__(parent)`, `_setup_ui()` (5-column table: SMILES, name, activity, type, source), `set_database(mol_db)`, `refresh()` (loads up to 500 records), `_show_context_menu(position)` (view details / export SMILES to clipboard).
- **Logic:** Molecule database browser. Table view with right-click context menu for viewing molecule details (opens MoleculeInfoDialog with rendered structure) or copying SMILES to clipboard.

---

## 82. `src/mbforge/ui/mol_renderer.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\ui\mol_renderer.py`
- **Lines:** 165
- **Imports:** Standard library: `io`, `pathlib.Path`, `typing`. PyQt6: `Qt`, `QPixmap`, `QLabel`, `QVBoxLayout`, `QWidget`. Deferred: `rdkit.Chem`, `rdkit.Chem.Draw`
- **Module-level variables:** `RDKIT_AVAILABLE`
- **Class `MoleculeRenderer` (line 30):** Static utility class.
  - **Class variable:** `DEFAULT_SIZE = (320, 240)`.
  - **Class methods:** `smiles_to_pixmap(smiles, size, legend) -> Optional[QPixmap]`, `smiles_to_file(smiles, path, size, legend) -> bool`.
- **Class `MoleculeImageWidget(QWidget)` (line 111):**
  - Methods: `__init__(smiles, size, parent)`, `_setup_ui()`, `set_smiles(smiles, legend)`, `clear()`.
- **Logic:** RDKit-to-Qt molecule rendering. Converts SMILES to 2D structure image via RDKit Draw, then to QPixmap for display in Qt widgets. Fallback text display when RDKit is unavailable or rendering fails.

---

## 83. `src/mbforge/ui/preview.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\ui\preview.py`
- **Lines:** 109
- **Imports:** Standard library: `typing`. Third-party: `markdown`. PyQt6: `QWebEngineSettings`, `QWebEngineView`, `QWidget`
- **Class `MarkdownPreview(QWebEngineView)` (line 13):**
  - Methods: `__init__(parent)` (initializes markdown converter with tables/fenced_code/toc/nl2br extensions, sets up base HTML template with CSS), `set_markdown(text)` (converts markdown to HTML, renders in web view).
- **Logic:** Real-time Markdown preview using QWebEngineView. Converts markdown to HTML with the `markdown` library and renders with a comprehensive CSS stylesheet (clean white theme, syntax-highlighted code blocks, styled tables/blockquotes).

---

## 84. `src/mbforge/ui/pdf_viewer.py`
- **Path:** `C:\Users\10954\Desktop\MBForge\src\mbforge\ui\pdf_viewer.py`
- **Lines:** 529
- **Imports:** Standard library: `atexit`, `concurrent.futures`, `pathlib.Path`, `typing`, `os`. Third-party: `fitz` (PyMuPDF). PyQt6: extensive imports.
- **Module-level variables:** `_NWORKERS`, `_executor` (global ThreadPoolExecutor, max 4 workers, shutdown at exit)
- **Function `_render_page_range(path, scale, indices) -> List[tuple]` (line 31):** Thread pool worker -- opens fitz.Document per thread, renders page range to QImage.
- **Class `PDFViewer(QWidget)` (line 51):**
  - Signals: `page_changed(int, int)`, `_pages_done(list)`.
  - **Class variable:** `BUFFER_PAGES = 5`.
  - **Attributes:** doc, _doc_path, current_page, _scale, _continuous_mode, _virtual_container, _page_heights/widths, _page_cache, _visible_widgets, _pending_indices, _all_indices_rendered, _rendered_count, _total_pages.
  - **Methods (25+):**
    - `__init__(parent)` (line 60): Sets up toolbar (mode toggle, prev/next, page input, zoom, progress bar) and scroll area.
    - `load_pdf(path)` (line 171): Opens PDF, precomputes page sizes, renders.
    - `_precompute_page_sizes()` (line 196)
    - `_render()` (line 210): Dispatches to continuous or single mode.
    - `_render_continuous_virtual()` (line 221): Creates virtual container, renders first screen, schedules re-render.
    - `_render_visible_range()` (line 241): Calculates visible page range from scroll position, recycles off-screen widgets, renders missing pages.
    - `_render_page_sync(index) -> bool` (line 290)
    - `_place_page_widget(index, pixmap)` (line 307): Positions QLabel widgets in virtual container at correct Y offset.
    - `_page_offset(index) -> int` (line 330)
    - `_start_background_render(indices)` (line 334): Submits to thread pool with progress tracking.
    - `_on_future_done(future)` (line 356)
    - `_on_pages_ready(batch)` (line 366): Converts QImage to QPixmap (must be on GUI thread), updates cache and UI.
    - `_is_index_visible(index) -> bool` (line 390)
    - `_on_scroll()` (line 401)
    - `_on_viewport_resize()` (line 406)
    - `_rerender_if_needed()` (line 411)
    - `_render_single()` (line 416)
    - `_clear_visible_widgets()` (line 433)
    - `_scroll_to_current_page()` (line 443)
    - `_update_toolbar()` (line 450)
    - `_jump_to_page_input()` (line 459)
    - `next_page()`, `prev_page()`, `zoom_in()`, `zoom_out()`
    - `_invalidate_and_reload()` (line 498): Full re-render on zoom change.
    - `close_document()` (line 513)
    - `eventFilter(obj, event)` (line 524): Intercepts viewport resize.
- **Logic:** High-performance PDF viewer with virtual scrolling. Only renders pages visible in the viewport (plus 5-page buffer). Uses a global thread pool (4 workers) for parallel page rendering. Each worker opens its own fitz.Document to avoid cross-thread sharing. Pages are rendered to QImage in workers, converted to QPixmap on the GUI thread, and positioned absolutely in a virtual container. Supports single-page and continuous scroll modes, zoom, and page navigation.

---

**END OF REPORT**