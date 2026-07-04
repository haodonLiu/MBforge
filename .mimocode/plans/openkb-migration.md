# MBForge: OpenKB + PageIndex Migration Plan

> **Status**: Draft
> **Date**: 2026-06-30
> **Scope**: Replace embed+rerank+Zvec KB with OpenKB wiki system

---

## Table of Contents

1. [Architecture Decision](#1-architecture-decision)
2. [LLM Configuration](#2-llm-configuration)
3. [Ingestion Pipeline Replacement](#3-ingestion-pipeline-replacement)
4. [Query Path Replacement](#4-query-path-replacement)
5. [Storage Mapping](#5-storage-mapping)
6. [Migration Strategy](#6-migration-strategy)
7. [Files to Modify](#7-files-to-modify)
8. [Dependency Changes](#8-dependency-changes)

---

## 1. Architecture Decision

### Recommendation: Option C — Thin Adapter Layer

Build a thin adapter layer (`src/mbforge/openkb/`) that wraps OpenKB's Python API. This is the best approach because:

| Criterion | Subprocess (A) | Direct Import (B) | Adapter Layer (C) |
|-----------|----------------|--------------------|--------------------|
| **Complexity** | High (IPC, process mgmt) | Low | Low-Medium |
| **Latency** | High (serialization) | Low | Low |
| **Isolation** | High | None | High |
| **Upgrade path** | Hard | Hard (leaky) | Easy |
| **Testability** | Hard | Medium | Easy |

**Why not Direct Import (B)?** OpenKB's API surface is spread across `pageindex`, `openkb.agent.compiler`, `openkb.agent.query`. Importing these directly into `knowledge_base.py` and `runner.py` creates tight coupling. If OpenKB's API changes, we'd need to touch many files.

**Why the Adapter Layer (C)?** The adapter:
1. **Isolates OpenKB's interface** — all OpenKB imports live in one place
2. **Maps OpenKB's data model to MBForge's** — OpenKB returns `str` (answer), MBForge expects `list[dict]` (results)
3. **Handles async bridging** — OpenKB is async, some MBForge paths are sync
4. **Provides fallback** — if OpenKB fails, we can fall back to legacy search

### Adapter Module Structure

```
src/mbforge/openkb/
├── __init__.py          # Public API exports
├── config.py            # LLM config → LiteLLM format mapping
├── indexer.py           # PageIndex wrapper (for tree indexing)
├── compiler.py          # Wiki compilation wrapper
├── query.py             # run_query wrapper + result formatting
└── adapter.py           # High-level facade (index_doc, search, etc.)
```

**Verified OpenKB API** (from GitHub README and source):
- `openkb add <file>` — CLI command to add documents
- `openkb query "question"` — CLI command to query the wiki
- `openkb.agent.query.run_query(question, kb_dir, model)` — Python API
- `openkb.agent.compiler.compile_long_doc(...)` — Python API for long docs
- `openkb.agent.compiler.compile_short_doc(...)` — Python API for short docs
- `openkb.indexer` — Document indexing module
- `openkb.config` — Configuration management
- Uses LiteLLM for LLM calls (supports OpenAI, Anthropic, Ollama, etc.)
- Uses OpenAI Agents SDK under the hood for query/chat

### Key Design Principle: Feature Flag

Use a config flag `kb_backend: "openkb" | "zvec"` to switch between backends. This allows:
- Gradual rollout
- Easy rollback
- Side-by-side comparison during development

---

## 2. LLM Configuration

### Config Schema

Extend `src/mbforge/utils/config.py` with a new `LLMConfig` model:

```python
# src/mbforge/utils/config.py (additions)

class LLMConfig(BaseModel):
    """LLM configuration for OpenKB and agent."""
    
    model_config = ConfigDict(extra="ignore")
    
    # Provider: "openai_compatible" | "ollama" | "litellm"
    provider: str = "openai_compatible"
    
    # Model name (LiteLLM format: "provider/model" or plain model name)
    model: str = "gpt-4o-mini"
    
    # API endpoint (OpenAI-compatible)
    base_url: str = ""
    
    # API key
    api_key: str = ""
    
    # Alternative: api_base (OpenAI SDK field name)
    api_base: str = ""
    
    # Generation parameters
    temperature: float = 0.7
    max_tokens: int = 4096
    
    # PageIndex-specific
    pageindex_threshold: int = 20  # Pages >= this triggers PageIndex
    language: str = "en"  # "en" | "zh" | "auto"


class AppConfig(BaseSettings):
    # ... existing fields ...
    embed: EmbedConfig = Field(default_factory=EmbedConfig)
    rerank: RerankConfig = Field(default_factory=RerankConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)  # NEW
    kb_backend: str = "openkb"  # NEW: "openkb" | "zvec"
    model_cache_dir: str = ""
```

### Environment Variables

| Variable | Config Field | Default |
|----------|-------------|---------|
| `MBFORGE_LLM_PROVIDER` | `llm.provider` | `"openai_compatible"` |
| `MBFORGE_LLM_MODEL` | `llm.model` | `"gpt-4o-mini"` |
| `MBFORGE_LLM_BASE_URL` | `llm.base_url` | `""` |
| `MBFORGE_LLM_API_KEY` | `llm.api_key` | `""` |
| `MBFORGE_LLM_API_BASE` | `llm.api_base` | `""` |
| `MBFORGE_LLM_TEMPERATURE` | `llm.temperature` | `0.7` |
| `MBFORGE_LLM_MAX_TOKENS` | `llm.max_tokens` | `4096` |
| `MBFORGE_LLM_PAGEINDEX_THRESHOLD` | `llm.pageindex_threshold` | `20` |
| `MBFORGE_LLM_LANGUAGE` | `llm.language` | `"en"` |
| `MBFORGE_KB_BACKEND` | `kb_backend` | `"openkb"` |

### LiteLLM Format Mapping

OpenKB uses LiteLLM for LLM calls. The adapter maps our config to LiteLLM's format:

```python
# src/mbforge/openkb/config.py

def to_litellm_config(cfg: LLMConfig) -> dict:
    """Map MBForge LLMConfig to LiteLLM model string."""
    if cfg.provider == "openai_compatible":
        # LiteLLM format: "openai/model?api_base=..."
        model = f"openai/{cfg.model}"
        if cfg.base_url:
            model += f"?api_base={cfg.base_url}"
        return {
            "model": model,
            "api_key": cfg.api_key,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
        }
    elif cfg.provider == "ollama":
        return {
            "model": f"ollama/{cfg.model}",
            "api_base": cfg.base_url or "http://localhost:11434",
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
        }
    else:
        # Direct passthrough
        return {
            "model": cfg.model,
            "api_key": cfg.api_key,
            "base_url": cfg.base_url,
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
        }
```

### Config Examples

**OpenAI API:**
```json
{
  "llm": {
    "provider": "openai_compatible",
    "model": "gpt-4o-mini",
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-..."
  }
}
```

**Local Ollama:**
```json
{
  "llm": {
    "provider": "ollama",
    "model": "qwen2.5:7b",
    "base_url": "http://localhost:11434"
  }
}
```

**Alibaba DashScope:**
```json
{
  "llm": {
    "provider": "openai_compatible",
    "model": "qwen-plus",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_key": "sk-..."
  }
}
```

---

## 3. Ingestion Pipeline Replacement

### Current Pipeline Stages

```
Stage 1: extract_text     → ExtractedDocument (raw_text, pages, title)
Stage 2: segment          → SegmentedDocument (sections, headings, tree)
Stage 3: enrich_molecules → dict (molecule_count, molecules)
Stage 4: persist          → filesystem (page texts, doc tree, report)
Stage 5: chunk+embed+index → Zvec collection
```

### New Pipeline Stages

```
Stage 1: extract_text     → ExtractedDocument (KEEP)
Stage 2: pageindex        → PageIndex tree index (REPLACES segment+chunk)
Stage 3: wiki_compile     → OpenKB wiki (REPLACES embed+index)
Stage 4: enrich_molecules → dict (KEEP)
Stage 5: persist          → filesystem (SIMPLIFIED)
```

### Stage Mapping

| Current Stage | New Stage | What Changes |
|--------------|-----------|--------------|
| `extract_text` | `extract_text` | **No change** — keep PyMuPDF + OCR |
| `segment` | `pageindex` | **Replaced** — PageIndex builds tree via LLM |
| `chunk` | (merged into pageindex) | **Removed** — PageIndex handles chunking |
| `embed` | (merged into wiki_compile) | **Removed** — OpenKB doesn't use embeddings |
| `index` (Zvec) | (merged into wiki_compile) | **Removed** — OpenKB uses wiki files |
| `enrich_molecules` | `enrich_molecules` | **No change** — MBForge-specific |
| `persist` | `persist` | **Simplified** — remove doc_trees.json |

### New Pipeline Runner

```python
# src/mbforge/pipeline/runner.py (modified)

async def run_pipeline(
    pdf_path: str,
    project_root: str,
    doc_id: str = "",
    on_progress: ProgressCallback | None = None,
) -> PipelineResult:
    """Run document processing pipeline.
    
    Dispatches to OpenKB or legacy pipeline based on config.
    """
    cfg = load_global_config()
    
    if cfg.kb_backend == "openkb":
        return await _run_pipeline_openkb(pdf_path, project_root, doc_id, on_progress)
    else:
        return _run_pipeline_legacy(pdf_path, project_root, doc_id, on_progress)


async def _run_pipeline_openkb(
    pdf_path: str,
    project_root: str,
    doc_id: str,
    on_progress: ProgressCallback | None = None,
) -> PipelineResult:
    """OpenKB pipeline: extract → PageIndex → wiki compile → enrich → persist."""
    start_time = time.monotonic()
    
    # Stage 1: Extract text (keep existing)
    _emit("progress", "Extracting text...", stage="extract")
    from .extract_text import extract_pdf_text
    extracted = extract_pdf_text(pdf_path)
    _emit("complete", f"Extracted {extracted.page_count} pages", stage="extract")
    
    # Stage 2: PageIndex indexing
    _emit("progress", "Building PageIndex tree...", stage="pageindex")
    from ..openkb.adapter import OpenKBAdapter
    adapter = OpenKBAdapter(project_root)
    openkb_doc_id = await adapter.index_document(pdf_path, doc_id)
    _emit("complete", f"PageIndex tree built", stage="pageindex")
    
    # Stage 3: Wiki compilation
    _emit("progress", "Compiling wiki...", stage="wiki")
    await adapter.compile_wiki(openkb_doc_id, doc_id)
    _emit("complete", "Wiki compiled", stage="wiki")
    
    # Stage 4: Enrich molecules (keep existing)
    _emit("progress", "Detecting molecules...", stage="enrich")
    enrich_result = _enrich_molecules(pdf_path, project_root, doc_id, extracted.page_count)
    _emit("complete", f"Detected {enrich_result.get('molecule_count', 0)} molecules", stage="enrich")
    
    # Stage 5: Persist (simplified)
    _emit("progress", "Saving document...", stage="persist")
    _persist_document(project_root, doc_id, extracted, enrich_result)
    _emit("complete", "Document saved", stage="persist")
    
    duration_ms = int((time.monotonic() - start_time) * 1000)
    return PipelineResult(
        doc_id=doc_id,
        page_count=extracted.page_count,
        section_count=0,  # OpenKB tracks this internally
        chunk_count=0,    # OpenKB doesn't use chunks
        indexed_count=1,  # One document indexed
        parser=extracted.parser,
        title=extracted.title,
        duration_ms=duration_ms,
    )
```

### OpenKB Adapter (Indexing)

```python
# src/mbforge/openkb/indexer.py

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..utils.config import load_global_config
from ..utils.logger import get_logger

logger = get_logger("mbforge.openkb.indexer")


class PageIndexWrapper:
    """Wrapper around PageIndexClient for document indexing."""
    
    def __init__(self, storage_path: str):
        self._storage_path = Path(storage_path)
        self._client: Any = None
    
    def _get_client(self) -> Any:
        """Lazy-initialize PageIndexClient."""
        if self._client is not None:
            return self._client
        
        cfg = load_global_config().llm
        
        try:
            from pageindex import PageIndexClient
            
            self._client = PageIndexClient(
                api_key=cfg.api_key,
                model=cfg.model,
                storage_path=str(self._storage_path),
            )
            return self._client
        except ImportError:
            raise RuntimeError(
                "pageindex package not installed. "
                "Run: uv add pageindex"
            )
    
    def add_document(self, pdf_path: str, doc_id: str = "") -> str:
        """Add a PDF to the PageIndex collection.
        
        Returns:
            OpenKB document ID
        """
        client = self._get_client()
        col = client.collection()
        
        # PageIndex uses its own doc_id generation
        # We pass doc_id as metadata for correlation
        openkb_doc_id = col.add(
            pdf_path,
            metadata={"mbforge_doc_id": doc_id} if doc_id else None,
        )
        
        logger.info("Indexed document: %s → %s", pdf_path, openkb_doc_id)
        return openkb_doc_id
    
    def get_document(self, openkb_doc_id: str) -> Any:
        """Get a document from the collection."""
        client = self._get_client()
        col = client.collection()
        return col.get_document(openkb_doc_id, include_text=True)
```

### OpenKB Adapter (Wiki Compilation)

```python
# src/mbforge/openkb/compiler.py

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..utils.config import load_global_config
from ..utils.logger import get_logger

logger = get_logger("mbforge.openkb.compiler")


class WikiCompiler:
    """Wrapper around OpenKB wiki compilation."""
    
    def __init__(self, wiki_dir: str):
        self._wiki_dir = Path(wiki_dir)
    
    async def compile_document(
        self,
        doc_name: str,
        doc_id: str,
        page_count: int,
    ) -> None:
        """Compile a document into the wiki.
        
        Uses compile_long_doc for documents with many pages,
        compile_short_doc for shorter ones.
        """
        cfg = load_global_config().llm
        
        try:
            from openkb.agent.compiler import compile_long_doc, compile_short_doc
        except ImportError:
            raise RuntimeError(
                "openkb package not installed. "
                "Run: uv add openkb"
            )
        
        summary_path = self._wiki_dir / "summaries" / f"{doc_id}.md"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        
        threshold = cfg.pageindex_threshold
        
        if page_count >= threshold:
            logger.info("Compiling long document: %s (%d pages)", doc_name, page_count)
            await compile_long_doc(
                doc_name=doc_name,
                summary_path=str(summary_path),
                doc_id=doc_id,
                kb_dir=str(self._wiki_dir),
                model=cfg.model,
            )
        else:
            logger.info("Compiling short document: %s (%d pages)", doc_name, page_count)
            await compile_short_doc(
                doc_name=doc_name,
                summary_path=str(summary_path),
                doc_id=doc_id,
                kb_dir=str(self._wiki_dir),
                model=cfg.model,
            )
```

### OpenKB Adapter (High-Level Facade)

```python
# src/mbforge/openkb/adapter.py

from __future__ import annotations

from pathlib import Path

from ..utils.config import load_global_config
from ..utils.logger import get_logger
from .indexer import PageIndexWrapper
from .compiler import WikiCompiler

logger = get_logger("mbforge.openkb.adapter")


class OpenKBAdapter:
    """High-level adapter for OpenKB operations."""
    
    def __init__(self, project_root: str):
        self._project_root = Path(project_root)
        self._openkb_dir = self._project_root / ".mbforge" / "openkb"
        self._wiki_dir = self._openkb_dir / "wiki"
        self._indexer: PageIndexWrapper | None = None
        self._compiler: WikiCompiler | None = None
    
    def _get_indexer(self) -> PageIndexWrapper:
        if self._indexer is None:
            self._indexer = PageIndexWrapper(str(self._openkb_dir))
        return self._indexer
    
    def _get_compiler(self) -> WikiCompiler:
        if self._compiler is None:
            self._compiler = WikiCompiler(str(self._wiki_dir))
        return self._compiler
    
    async def index_document(self, pdf_path: str, doc_id: str = "") -> str:
        """Index a PDF document using PageIndex."""
        indexer = self._get_indexer()
        return indexer.add_document(pdf_path, doc_id)
    
    async def compile_wiki(self, openkb_doc_id: str, doc_id: str) -> None:
        """Compile the wiki for an indexed document."""
        indexer = self._get_indexer()
        doc = indexer.get_document(openkb_doc_id)
        
        compiler = self._get_compiler()
        page_count = getattr(doc, "page_count", 0)
        await compiler.compile_document(
            doc_name=doc.name,
            doc_id=doc_id,
            page_count=page_count,
        )
    
    async def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> dict:
        """Search the wiki using OpenKB's query agent."""
        from .query import search_wiki
        return await search_wiki(
            query=query,
            wiki_dir=str(self._wiki_dir),
            top_k=top_k,
        )
```

---

## 4. Query Path Replacement

### Current Query Path

```
knowledge_base.search(query)
  → check_cache(query)
  → embed query (qwen3_embed.embed)
  → Zvec hybrid_search (vector + FTS + RRF)
  → rerank (qwen3_rerank.rerank)
  → store_cache(query, results)
  → return {results, from_cache, count}
```

### New Query Path

```
knowledge_base.search(query)
  → check_cache(query)
  → OpenKB run_query(query, wiki_dir, model)
  → parse answer + extract source sections
  → format results (answer as primary, sources as supplementary)
  → store_cache(query, results)
  → return {results, answer, from_cache, count}
```

### Key Challenge: Mapping OpenKB Output to MBForge's Result Format

**OpenKB returns**: `str` (natural language answer)

**MBForge expects**: `list[dict]` with `{id, text, metadata, score}`

**Solution**: Two-part response

1. **Primary result**: The OpenKB answer (as a special result with `type: "answer"`)
2. **Supplementary results**: Source sections from the wiki (as regular results)

### Query Implementation

```python
# src/mbforge/openkb/query.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..utils.config import load_global_config
from ..utils.logger import get_logger

logger = get_logger("mbforge.openkb.query")


async def search_wiki(
    query: str,
    wiki_dir: str,
    top_k: int = 10,
) -> dict[str, Any]:
    """Search the OpenKB wiki.
    
    Returns:
        {
            "results": [...],  # Source sections
            "answer": str,     # OpenKB's answer
            "count": int,
        }
    """
    cfg = load_global_config().llm
    
    try:
        from openkb.agent.query import run_query
    except ImportError:
        raise RuntimeError("openkb package not installed")
    
    # Run OpenKB query
    answer = await run_query(
        question=query,
        kb_dir=wiki_dir,
        model=cfg.model,
    )
    
    # Extract source sections from wiki
    sources = _extract_relevant_sources(query, wiki_dir, top_k)
    
    # Format results
    results = []
    
    # Add source sections as results
    for source in sources:
        results.append({
            "id": source["id"],
            "text": source["text"],
            "metadata": {
                "doc_id": source.get("doc_id", ""),
                "page_start": source.get("page_start"),
                "page_end": source.get("page_end"),
                "section_title": source.get("title", ""),
                "path": source.get("path", ""),
                "type": "source",
            },
            "score": source.get("score", 0.5),
        })
    
    return {
        "results": results[:top_k],
        "answer": answer,
        "count": len(results),
    }


def _extract_relevant_sources(
    query: str,
    wiki_dir: str,
    top_k: int,
) -> list[dict]:
    """Extract relevant source sections from wiki files.
    
    This is a simple keyword-based search over wiki markdown files.
    For production, consider using OpenKB's tree navigation.
    """
    wiki_path = Path(wiki_dir)
    sources_dir = wiki_path / "sources"
    
    if not sources_dir.exists():
        return []
    
    query_lower = query.lower()
    query_terms = set(query_lower.split())
    
    scored_sources = []
    
    for md_file in sources_dir.glob("**/*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            content_lower = content.lower()
            
            # Simple relevance scoring
            score = 0.0
            for term in query_terms:
                if term in content_lower:
                    score += content_lower.count(term)
            
            if score > 0:
                # Parse markdown for metadata
                metadata = _parse_source_metadata(content, md_file)
                
                scored_sources.append({
                    "id": md_file.stem,
                    "text": content[:2000],  # Truncate for display
                    "score": min(score / (len(query_terms) * 10), 1.0),
                    **metadata,
                })
        except Exception as e:
            logger.warning("Failed to read source %s: %s", md_file, e)
    
    # Sort by score and return top_k
    scored_sources.sort(key=lambda x: x["score"], reverse=True)
    return scored_sources[:top_k]


def _parse_source_metadata(content: str, file_path: Path) -> dict:
    """Parse metadata from markdown source file."""
    metadata = {
        "doc_id": file_path.stem,
        "page_start": None,
        "page_end": None,
        "title": "",
        "path": "",
    }
    
    # Try to extract title from first heading
    for line in content.split("\n")[:10]:
        if line.startswith("# "):
            metadata["title"] = line[2:].strip()
            break
    
    # Try to extract page numbers from content
    import re
    page_match = re.search(r"page[s]?\s*(\d+)(?:\s*[-–]\s*(\d+))?", content, re.IGNORECASE)
    if page_match:
        metadata["page_start"] = int(page_match.group(1))
        if page_match.group(2):
            metadata["page_end"] = int(page_match.group(2))
    
    return metadata
```

### Modified knowledge_base.py

```python
# src/mbforge/core/knowledge_base.py (modified)

async def search(
    query: str,
    project_root: str,
    top_k: int = 10,
    doc_id_filter: str | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Hybrid knowledge base search.
    
    Dispatches to OpenKB or legacy search based on config.
    """
    from ..utils.config import load_global_config
    cfg = load_global_config()
    
    if cfg.kb_backend == "openkb":
        return await _search_openkb(query, project_root, top_k, doc_id_filter, use_cache)
    else:
        return _search_legacy(query, project_root, top_k, doc_id_filter, use_cache)


async def _search_openkb(
    query: str,
    project_root: str,
    top_k: int,
    doc_id_filter: str | None,
    use_cache: bool,
) -> dict[str, Any]:
    """OpenKB search path."""
    from .semantic_cache import check_cache, store_cache
    from ..openkb.adapter import OpenKBAdapter
    
    # Cache check
    if use_cache:
        cached = check_cache(query, project_root)
        if cached is not None:
            return {"results": cached, "from_cache": True, "count": len(cached)}
    
    # OpenKB search
    adapter = OpenKBAdapter(project_root)
    result = await adapter.search(query, top_k=top_k)
    
    results = result.get("results", [])
    answer = result.get("answer", "")
    
    # Add answer as a special result at the beginning
    if answer:
        results.insert(0, {
            "id": "openkb_answer",
            "text": answer,
            "metadata": {
                "type": "answer",
                "source": "openkb",
            },
            "score": 1.0,
        })
    
    # Apply doc_id filter if specified
    if doc_id_filter:
        results = [
            r for r in results
            if r.get("metadata", {}).get("doc_id") == doc_id_filter
            or r.get("id") == "openkb_answer"
        ]
    
    # Cache results
    if use_cache and results:
        store_cache(query, project_root, results)
    
    return {"results": results[:top_k], "from_cache": False, "count": len(results)}


def _search_legacy(
    query: str,
    project_root: str,
    top_k: int,
    doc_id_filter: str | None,
    use_cache: bool,
) -> dict[str, Any]:
    """Legacy search path (embed + Zvec + rerank)."""
    # ... existing implementation unchanged ...
```

### API Contract Update

```python
# src/mbforge/routers/knowledge_base.py (modified)

@router.post("/search")
async def kb_search(body: dict) -> dict:
    query = body.get("query", "")
    top_k = body.get("top_k", 10)
    project_root = body.get("project_root", "")
    doc_id_filter = body.get("doc_id_filter")
    
    if not query or not project_root:
        return {"success": False, "results": []}
    
    try:
        from ..core.knowledge_base import search
        
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: search(query, project_root, top_k=top_k, doc_id_filter=doc_id_filter),
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error("KB search failed: %s", e)
        return {"success": False, "error": str(e), "results": []}
```

**Response format change**: Added `answer` field to response:

```json
{
    "success": true,
    "results": [
        {
            "id": "openkb_answer",
            "text": "The answer from OpenKB...",
            "metadata": {"type": "answer"},
            "score": 1.0
        },
        {
            "id": "section_123",
            "text": "Source section...",
            "metadata": {"doc_id": "paper_1", "page_start": 5, "type": "source"},
            "score": 0.85
        }
    ],
    "answer": "The answer from OpenKB...",
    "count": 2,
    "from_cache": false
}
```

### Frontend Adaptation

```typescript
// frontend/src/api/tauri/kb.ts (modified)

export interface KbSearchResult {
  id: string
  text: string
  metadata: Record<string, unknown>
  score: number
}

export interface KbSearchResponse {
  success: boolean
  results: KbSearchResult[]
  answer?: string  // NEW: OpenKB answer
  count: number
  from_cache: boolean
}

export async function kbSearch(
  projectRoot: string,
  query: string,
  topK = 5,
): Promise<KbSearchResult[]> {
  const resp = await invokeWithError(
    () => httpPost<KbSearchResponse>('/api/v1/kb/search', {
      project_root: projectRoot,
      query,
      top_k: topK,
    }),
    ErrorCode.ApiError,
  )
  return resp.results
}

// NEW: Get answer separately for display
export async function kbSearchWithAnswer(
  projectRoot: string,
  query: string,
  topK = 5,
): Promise<{ results: KbSearchResult[]; answer: string }> {
  const resp = await invokeWithError(
    () => httpPost<KbSearchResponse>('/api/v1/kb/search', {
      project_root: projectRoot,
      query,
      top_k: topK,
    }),
    ErrorCode.ApiError,
  )
  return {
    results: resp.results,
    answer: resp.answer ?? '',
  }
}
```

---

## 5. Storage Mapping

### Current Storage Layout

```
{project_root}/
├── .mbforge/
│   ├── knowledge_base.db     # SQLite (semantic_cache, figure_labels, coref_predictions)
│   ├── search.zvec/          # Zvec collection (dense + FTS5)
│   └── ...
├── index/
│   ├── pages/{doc_id}/       # Page text files (page_0001.txt, ...)
│   └── doc_trees.json        # Document tree structures
└── projects/{doc_id}/        # Project reports
```

### New Storage Layout

```
{project_root}/
├── .mbforge/
│   ├── knowledge_base.db     # KEEP (semantic_cache, figure_labels, coref_predictions)
│   ├── openkb/               # NEW (replaces search.zvec/)
│   │   ├── .openkb/
│   │   │   ├── config.yaml   # OpenKB configuration
│   │   │   └── hashes.json   # Document hash tracking
│   │   ├── raw/              # Original files (symlinks or copies)
│   │   └── wiki/
│   │       ├── index.md      # Wiki index
│   │       ├── log.md        # Activity log
│   │       ├── AGENTS.md     # Agent instructions
│   │       ├── summaries/    # Per-document summaries
│   │       │   └── {doc_id}.md
│   │       ├── sources/      # Document content
│   │       │   └── {doc_id}/
│   │       │       └── page_{N}.md
│   │       ├── concepts/     # Cross-document topics
│   │       ├── entities/     # Named things
│   │       └── explorations/ # Saved queries
│   └── ... (other .mbforge files)
├── index/
│   ├── pages/{doc_id}/       # KEEP (page texts for get_document_pages API)
│   └── ... (remove doc_trees.json)
└── projects/{doc_id}/        # KEEP (project reports)
```

### Storage Coexistence

- **`knowledge_base.db`**: KEEP — still needed for semantic_cache, figure_labels, coref_predictions
- **`search.zvec/`**: REMOVE — replaced by `openkb/wiki/`
- **`openkb/`**: NEW — contains PageIndex data and wiki
- **`index/pages/`**: KEEP — still needed for `get_document_pages()` API
- **`index/doc_trees.json`**: REMOVE — OpenKB maintains its own tree structure

### Migration of Existing Data

For existing projects with Zvec indexes:
1. Keep `search.zvec/` in place (don't delete)
2. Re-index documents using OpenKB pipeline
3. Once migration is complete, users can manually delete `search.zvec/`

The `kb_backend` config flag controls which backend is used:
- `"openkb"`: Uses `openkb/wiki/` for search
- `"zvec"`: Uses `search.zvec/` for search (legacy)

---

## 6. Migration Strategy

### Phase 1: Foundation (Week 1)

**Goal**: Add OpenKB dependencies and config, create adapter module structure.

**Tasks**:
1. Add `openkb` and `pageindex` to `pyproject.toml` dependencies
2. Extend `LLMConfig` in `src/mbforge/utils/config.py`
3. Add environment variables to `src/mbforge/utils/constants.py`
4. Create `src/mbforge/openkb/` module structure
5. Implement `config.py` (LiteLLM format mapping)
6. Implement `indexer.py` (PageIndexClient wrapper)
7. Write unit tests for config mapping

**Deliverables**:
- `src/mbforge/openkb/__init__.py`
- `src/mbforge/openkb/config.py`
- `src/mbforge/openkb/indexer.py`
- Updated `pyproject.toml`
- Updated `src/mbforge/utils/config.py`
- Updated `src/mbforge/utils/constants.py`
- Tests: `tests/unit/test_openkb_config.py`

### Phase 2: Ingestion Pipeline (Week 2)

**Goal**: Replace pipeline stages with OpenKB indexing and wiki compilation.

**Tasks**:
1. Implement `compiler.py` (wiki compilation wrapper)
2. Implement `adapter.py` (high-level facade)
3. Modify `pipeline/runner.py` to support OpenKB mode
4. Simplify `pipeline/runner.py:_persist_document()` for OpenKB
5. Add feature flag dispatch in `run_pipeline()`
6. Update pipeline router to handle async
7. Write integration tests for OpenKB pipeline

**Deliverables**:
- `src/mbforge/openkb/compiler.py`
- `src/mbforge/openkb/adapter.py`
- Modified `src/mbforge/pipeline/runner.py`
- Modified `src/mbforge/routers/pipeline.py`
- Tests: `tests/integration/test_openkb_pipeline.py`

### Phase 3: Query Path (Week 3)

**Goal**: Replace search with OpenKB wiki-based query.

**Tasks**:
1. Implement `query.py` (run_query wrapper + result formatting)
2. Modify `core/knowledge_base.py` to dispatch to OpenKB
3. Implement `_search_openkb()` function
4. Implement `_extract_relevant_sources()` for source extraction
5. Update API response format to include `answer` field
6. Update semantic cache for new result format
7. Update agent tools to work with OpenKB search
8. Write tests for OpenKB search

**Deliverables**:
- `src/mbforge/openkb/query.py`
- Modified `src/mbforge/core/knowledge_base.py`
- Modified `src/mbforge/routers/knowledge_base.py`
- Modified `src/mbforge/agent/tools.py`
- Tests: `tests/integration/test_openkb_search.py`

### Phase 4: Cleanup & Backend Removal (Week 4)

**Goal**: Remove legacy components, make Zvec/qwen3 optional.

**Tasks**:
1. Make `pipeline/chunk.py` optional (keep for legacy mode)
2. Make `pipeline/index.py` optional (keep for legacy mode)
3. Make `backends/zvec_backend.py` optional (keep for legacy mode)
4. Update `backends/__init__.py` to lazy-load Zvec
5. Update `app.py` lifespan (remove zvec prewarm when using OpenKB)
6. Add migration utility for existing projects
7. Update documentation

**Deliverables**:
- Modified `src/mbforge/pipeline/chunk.py` (optional import)
- Modified `src/mbforge/pipeline/index.py` (optional import)
- Modified `src/mbforge/backends/__init__.py`
- Modified `src/mbforge/app.py`
- `scripts/migrate_to_openkb.py` (migration utility)
- Updated `AGENTS.md` and `README.md`

### Phase 5: Frontend Adaptation (Week 5)

**Goal**: Update frontend to display OpenKB answers.

**Tasks**:
1. Update `frontend/src/api/tauri/kb.ts` types
2. Add `kbSearchWithAnswer()` function
3. Update `SearchTab.tsx` to display answer
4. Add answer component with markdown rendering
5. Update SSE streaming for new format
6. Test end-to-end search flow
7. Update documentation

**Deliverables**:
- Modified `frontend/src/api/tauri/kb.ts`
- Modified `frontend/src/components/SearchTab.tsx`
- New: `frontend/src/components/OpenKBAnswer.tsx`
- Tests: `frontend/src/__tests__/SearchTab.test.tsx`

### Phase 6: Testing & Validation (Week 6)

**Goal**: Comprehensive testing, performance validation, documentation.

**Tasks**:
1. End-to-end testing with real PDFs
2. Performance benchmarking (OpenKB vs Zvec)
3. Accuracy comparison on test queries
4. Load testing with concurrent users
5. Edge case testing (empty docs, OCR, multi-language)
6. Update `docs/pageindex-research.md` with migration results
7. Write migration guide for existing users

**Deliverables**:
- Test results document
- Performance comparison report
- Updated documentation
- `docs/openkb-migration-guide.md`

---

## 7. Files to Modify

### New Files

| File | Purpose |
|------|---------|
| `src/mbforge/openkb/__init__.py` | Module exports |
| `src/mbforge/openkb/config.py` | LLM config → LiteLLM format mapping |
| `src/mbforge/openkb/indexer.py` | PageIndexClient wrapper |
| `src/mbforge/openkb/compiler.py` | Wiki compilation wrapper |
| `src/mbforge/openkb/query.py` | run_query wrapper + result formatting |
| `src/mbforge/openkb/adapter.py` | High-level facade |
| `tests/unit/test_openkb_config.py` | Config mapping tests |
| `tests/integration/test_openkb_pipeline.py` | Pipeline integration tests |
| `tests/integration/test_openkb_search.py` | Search integration tests |
| `scripts/migrate_to_openkb.py` | Migration utility |
| `docs/openkb-migration-guide.md` | Migration guide |
| `frontend/src/components/OpenKBAnswer.tsx` | Answer display component |

### Modified Files

| File | Changes |
|------|---------|
| `pyproject.toml` | Add openkb, pageindex dependencies |
| `src/mbforge/utils/config.py` | Add LLMConfig, kb_backend field |
| `src/mbforge/utils/constants.py` | Add LLM default constants |
| `src/mbforge/pipeline/runner.py` | Add OpenKB pipeline dispatch |
| `src/mbforge/pipeline/chunk.py` | Make optional (lazy import) |
| `src/mbforge/pipeline/index.py` | Make optional (lazy import) |
| `src/mbforge/core/knowledge_base.py` | Add OpenKB search dispatch |
| `src/mbforge/routers/knowledge_base.py` | Add answer field to response |
| `src/mbforge/routers/pipeline.py` | Handle async pipeline |
| `src/mbforge/app.py` | Update lifespan (conditional zvec prewarm) |
| `src/mbforge/backends/__init__.py` | Lazy-load Zvec |
| `src/mbforge/agent/tools.py` | Update kb_search for OpenKB |
| `frontend/src/api/tauri/kb.ts` | Add answer field, kbSearchWithAnswer() |
| `frontend/src/components/SearchTab.tsx` | Display OpenKB answer |

### Optional Files (Keep for Legacy Mode)

| File | Status |
|------|--------|
| `src/mbforge/pipeline/chunk.py` | Keep, make import optional |
| `src/mbforge/pipeline/index.py` | Keep, make import optional |
| `src/mbforge/pipeline/segment.py` | Keep, make import optional |
| `src/mbforge/backends/zvec_backend.py` | Keep, make import optional |
| `src/mbforge/backends/qwen3.py` | Keep (still used by MolScribe) |

---

## 8. Dependency Changes

### Add

```toml
# pyproject.toml additions

[project]
dependencies = [
    # ... existing dependencies ...
    
    # OpenKB + PageIndex (new)
    # OpenKB: CLI + Python API for wiki compilation and query
    # PageIndex: Vectorless, reasoning-based document tree indexing
    "openkb>=0.4.0",     # Latest: v0.4.2 (Jun 27, 2026)
    "pageindex>=0.1.0",  # From VectifyAI/PageIndex
]
```

**Package details**:
- `openkb` — Install via `pip install openkb` or `uv add openkb`
  - Provides: `openkb add`, `openkb query`, `openkb chat`, etc.
  - Python API: `openkb.agent.query`, `openkb.agent.compiler`, `openkb.indexer`
  - Dependencies: LiteLLM, OpenAI Agents SDK, markitdown, watchdog
- `pageindex` — Install via `pip install pageindex` or `uv add pageindex`
  - Provides: `PageIndexClient` for tree indexing
  - Used by OpenKB for long documents (PDFs ≥ 20 pages)

### Keep (All Existing)

All current dependencies remain for backward compatibility and other subsystems:

| Dependency | Reason to Keep |
|-----------|---------------|
| `sentence-transformers` | Used by MolScribe (timm dependency) |
| `transformers` | Used by MolScribe, MolDet |
| `torch`, `torchvision`, `torchaudio` | Used by MolScribe, MolDet |
| `zvec` | Optional, keep for legacy mode |
| `openai` | Used by EmbedBackend (openai_compatible provider) |
| `langchain`, `langgraph` | Used by agent |
| `pymupdf` | Used by extract_text (keep) |
| All others | No change |

### Make Optional

The following are no longer required for the primary KB path, but kept for backward compatibility:

| Dependency | Status |
|-----------|--------|
| `zvec` | Optional (only needed for legacy `kb_backend: "zvec"`) |
| `sentence-transformers` | Keep (MolScribe dependency) |

### Remove (None)

No dependencies need to be removed. All existing dependencies serve other subsystems or provide backward compatibility.

---

## Appendix A: Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| OpenKB API instability | Medium | High | Adapter layer isolates changes |
| LLM cost increase | High | Medium | Cache aggressively, use cheap models for indexing |
| Search latency increase | Medium | Medium | Cache results, parallel source extraction |
| Frontend breakage | Low | High | Maintain API contract, add `answer` field only |
| Data loss during migration | Low | Critical | Keep legacy backend, don't delete old data |
| OpenKB installation issues | Medium | Low | Provide clear install instructions |

## Appendix B: Performance Considerations

### Indexing Cost

- **PageIndex**: LLM call per document (for tree generation)
- **Wiki compilation**: LLM call per document (for summaries)
- **Total**: ~2 LLM calls per document at index time

**Mitigation**: Cache indexed documents, don't re-index unchanged files.

### Query Cost

- **OpenKB query**: LLM call per query (for reasoning)
- **Source extraction**: File reads (negligible)

**Mitigation**: Aggressive caching, use cheaper models for queries.

### Latency

- **Indexing**: Seconds to minutes (depending on document size)
- **Query**: 1-5 seconds (LLM call latency)

**Mitigation**: Show streaming results, cache frequent queries.

## Appendix C: Testing Strategy

### Unit Tests

- Config mapping (LLMConfig → LiteLLM format)
- Source extraction (wiki markdown parsing)
- Result formatting (OpenKB output → MBForge format)

### Integration Tests

- PageIndex indexing (real PDF → tree)
- Wiki compilation (real document → wiki files)
- Search flow (query → results + answer)
- Cache hit/miss behavior

### End-to-End Tests

- Full pipeline: PDF → index → search → answer
- Multiple documents
- Cross-document search
- Edge cases (empty docs, OCR, multi-language)

### Performance Tests

- Indexing throughput (docs/minute)
- Query latency (p50, p95, p99)
- Cache hit rate
- Memory usage

---

*This plan is a living document. Update as implementation progresses.*
