# CLAUDE.md — Repository-Level AI Context

> Per-repo quick-reference for AI coding assistants. Session-level personal rules
> live in `~/.claude/CLAUDE.md` (loaded automatically). This file is the
> **repository** mirror — it captures the live architecture and conventions so
> agents can orient quickly.

> **Last sync**: 2026-06-29, after the Rust→Python migration (commit 4b70ae8).
> If you find drift between this file and the code, **the code wins**; fix this
> file in the same PR.

---

## 1. What MBForge Is

Desktop knowledge-work platform for molecular science / drug discovery.
Ingests scientific PDFs, extracts molecules and activities, indexes them into a
searchable knowledge base, and exposes an AI agent for cross-document reasoning.

```
PDF → classify → extract → segment → chunk → index
                                    ↓
                              knowledge base (SQLite + Zvec)
                                    ↓
                        agent chat + molecule ops (FastAPI)
```

---

## 2. Stack (post-migration, 2026-06-29)

| Layer | Tech | Notes |
|---|---|---|
| Frontend | React 19 + Vite 8 + TypeScript 6 | Browser only. No Tauri shell. |
| Backend | FastAPI on `127.0.0.1:18792` | Single Python process. `uvicorn mbforge.app:app` |
| Agent | LangGraph (`>=0.4.0`) + langchain 0.3+ | 5 tools, multi-session, SSE streaming |
| Embed / Rerank | Qwen3-0.6B (local sentence-transformers) | Lazy-loaded on first use |
| MolDet | YOLO26n (`moldet_v2_yolo26n_960_doc.pt`) | conf_threshold = 0.5 |
| MolScribe | Swin Transformer + Transformer decoder | image → SMILES |
| Vector store | Zvec (`dense + FTS5 + hybrid RRF`) | per-project `.mbforge/search.zvec/` |
| ORM / DB | sqlite3 stdlib | per-project `.mbforge/knowledge_base.db` |
| Molecule | RDKit (Python) | SMILES canonicalization, fingerprints |
| PDF | pdfplumber / pypdfium2 | text + image extraction |
| Package manager | uv (Python) + npm (frontend) | `uv.lock` and `package-lock.json` are source of truth |

**Removed**: Tauri v2, Rust workspace (`src-tauri/`), chematic, lopdf, rusqlite,
ChromaDB. Code is in git history if you need to reference it.

---

## 3. Top-Level Layout

```
MBForge/
├── frontend/                       React + Vite app
│   ├── src/
│   │   ├── api/
│   │   │   ├── http/               HTTP bridge (replaces api/tauri for invoke())
│   │   │   └── sse.ts              SSE streaming client
│   │   ├── components/             Page-level + ui/ atoms
│   │   ├── context/AppContext.tsx  Global state
│   │   ├── hooks/                  useTheme, useAnimations, useToast
│   │   └── utils/errors.ts         AppError + ErrorCode (shared with API)
│   └── index.html
├── src/mbforge/                    Python FastAPI app
│   ├── app.py                      App entry — 53 routes, 12 routers
│   ├── server.py                   Dev server entry (uvicorn target)
│   ├── __main__.py                 `python -m mbforge`
│   ├── routers/                    12 FastAPI routers
│   │   ├── agent.py                LangGraph chat (SSE)
│   │   ├── pipeline.py             Document processing
│   │   ├── knowledge_base.py       KB search/stream
│   │   ├── molecule.py             SMILES / fingerprint ops
│   │   ├── chem.py                 Cheminformatics
│   │   ├── documents.py            CRUD
│   │   ├── project.py              Project management
│   │   ├── settings.py             Settings UI
│   │   ├── notes.py                Notes
│   │   ├── detection_cache.py      MolDet result cache
│   │   ├── environment.py          Env info / model status
│   │   └── events.py               Server-sent events hub
│   ├── agent/                      LangGraph agent
│   │   ├── graph.py                Graph definition
│   │   ├── llm_factory.py          Multi-provider LLM factory
│   │   ├── sessions.py             Session store
│   │   └── tools.py                5 agent tools
│   ├── core/                       Business core
│   │   ├── database.py             SQLite business tables
│   │   ├── project.py              Project lifecycle
│   │   ├── knowledge_base.py       KB CRUD + RRF fusion
│   │   ├── semantic_cache.py       Semantic cache
│   │   └── resource_manager.py     Models / downloads
│   ├── pipeline/                   5-stage PDF pipeline
│   │   ├── classify.py             Document type detection
│   │   ├── extract_text.py         Text + image extraction
│   │   ├── segment.py              Section segmentation
│   │   ├── chunk.py                Chunking for KB indexing
│   │   ├── index.py                Zvec indexing
│   │   └── runner.py               Pipeline orchestrator
│   ├── backends/                   Local model backends
│   │   ├── qwen3.py                EmbeddingProvider + OpenAI compatible
│   │   ├── molscribe.py            Molecule OCR
│   │   ├── moldet.py               MolDet (YOLO26)
│   │   └── zvec_backend.py         Zvec wrapper
│   ├── parsers/molecule/           Molecule-specific parsers
│   │   ├── coords.py
│   │   └── coref_alt.py            Cross-page coreference (tested)
│   ├── chem/                       Cheminformatics utilities
│   ├── models/                     Pydantic models (common, project)
│   └── utils/                      logger, config, helpers, constants
├── tests/
│   ├── unit/
│   │   └── parsers/test_coref_alt.py
│   ├── integration/
│   └── conftest.py
├── configs/                        YAML configs (constants, OCR)
├── docs/                           Specs, plans, references
├── assets/icon/                    Icon sources (SVG + master PNG)
├── assets/models/                  Dev model fixtures (gitignored)
├── TODO/INDEX.md                   Master task board
├── pyproject.toml                  uv + ruff + pytest
├── uv.lock
├── LICENSE                         CC BY-NC-SA 4.0
└── README.md
```

---

## 4. Run Commands

```bash
# Install
uv sync --dev                  # Python deps
npm --prefix frontend install   # Frontend deps

# Run (2 terminals)
uv run uvicorn mbforge.app:app --host 127.0.0.1 --port 18792
cd frontend && npm run dev

# Lint / typecheck / format
uv run ruff check src/
uv run ruff format src/ --check
cd frontend && npx tsc --noEmit

# Tests
uv run pytest tests/ -v
cd frontend && npm run test
```

Frontend dev server proxies `/api/*` → `127.0.0.1:18792`. No need to CORS.

---

## 5. Frontend → Backend Contract

Frontend **never** uses Tauri IPC anymore. All calls go through `httpFetch()`
(see `frontend/src/api/http/_utils.ts`). Streaming uses `sse.ts` for SSE.

```ts
// Old (deleted)
import { invoke } from '@tauri-apps/api/core'
await invoke('kb_search', { query, topK })

// New
import { httpFetch } from '@/api/http/_utils'
const results = await httpFetch<KbSearchResult[]>('/api/v1/kb/search', {
  method: 'POST',
  body: { query, top_k: 10 }
})
```

**Rules**:

- `import type` for type-only imports.
- Errors come back as `{ success: false, error, error_code }`. Use
  `AppError.fromResponse()` from `@/utils/errors`.
- SSE consumers must handle `event: error` frames and reconnect on disconnect.

---

## 6. Backend Conventions

- **Logger**: every module `from ..utils.logger import get_logger; logger = get_logger(__name__)`. Never `print()`.
- **Errors**: inherit from `MBForgeError` (`src/mbforge/utils/helpers.py`) with
  `status_code` + `error_code`. No bare `except:`.
- **Async I/O**: wrap blocking calls with `await loop.run_in_executor(None, lambda: ...)`.
- **Type hints**: `from __future__ import annotations`. Public functions fully annotated.
- **Routers**: prefix `/api/v1/{resource}`; if new resource, create `routers/{name}.py` and wire in `app.py`.
- **State**: `app.state` for shared singletons; never module-level mutable globals.
- **Pydantic models**: `src/mbforge/models/` for shared schemas; per-router
  models live next to the router.

---

## 7. Common Tasks

### Add a new REST endpoint

1. Define Pydantic request/response in `src/mbforge/models/` (or inline if router-local).
2. Add handler in the appropriate `routers/{name}.py`.
3. Wire into `src/mbforge/app.py` router includes (the list at the top of
   `app.py` is the single source of truth — keep it sorted).
4. Add `httpFetch()` wrapper in `frontend/src/api/http/{name}.ts`.

### Add an agent tool

1. Implement `BaseTool` subclass in `src/mbforge/agent/tools.py`.
2. Register in the tool list at the top of `tools.py`.
3. Update the system prompt in `agent/graph.py` if the tool needs discovery hints.

### Add a pipeline stage

1. Create `src/mbforge/pipeline/{stage}.py` with a `run(context) -> StageResult` function.
2. Wire into `pipeline/runner.py` stage list.
3. Add a `pipelines_{stage}_run` event in `routers/events.py` if you need progress streaming.

---

## 8. Storage Layout (per project)

```
{project_root}/
├── index/                         Pipeline output
├── .mbforge/
│   ├── knowledge_base.db          SQLite business tables
│   ├── search.zvec/               Zvec dense + FTS5 collection
│   └── cache/semantic_cache.json
└── assets/                        User-uploaded PDFs
```

Global config: `~/.config/MBForge/config.json` (Linux) /
`%APPDATA%\MBForge\config\config.json` (Windows).

---

## 9. Configuration Precedence

`MBFORGE_*` env vars > `~/.config/MBForge/config.json` > defaults.

LLM providers: `MBFORGE_LLM_PROVIDER`, `MBFORGE_LLM_API_KEY`, `MBFORGE_LLM_BASE_URL`.
Embeddings: `MBFORGE_EMBED_PROVIDER`, `MBFORGE_EMBED_MODEL`.

See `.env.template` (root) for the full list.

---

## 10. Don't Do

- ❌ Add Tauri, Rust, or any new compiled-language dependency without an ADR.
- ❌ Block the FastAPI event loop with sync I/O. Use `run_in_executor`.
- ❌ Use `print()` anywhere in `src/`.
- ❌ Catch `Exception:` without re-raising or logging the traceback.
- ❌ Create tests that mock the real backend — use `tmp_path` + real SQLite.
- ❌ Touch `pyproject.toml` dependency floors without bumping `uv.lock` in the same commit.

---

## 11. Pointers

- **Architecture**: this file + `docs/specs/architecture-conventions.md`
- **Molecule representation**: `docs/specs/molecular-representation.md`
- **E-SMILES spec**: `docs/specs/esmiles-spec.md`
- **MoleCode spec**: `docs/specs/molecode-spec.md`
- **Task board**: `TODO/INDEX.md` (P0–P3, status per item)
- **Code style**: `docs/specs/code-style.md`
- **LLM extraction reference**: `docs/specs/llm-chemical-extraction-reference.md`