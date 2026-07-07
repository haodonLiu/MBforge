# Repository Guidelines

> Practical guide for AI assistants working on MBForge. Covers architecture,
> conventions, and the day-to-day commands needed to add a feature, fix a bug,
> or run tests.

> **Snapshot**: 2026-07-05 — Python-only backend. The legacy `src-tauri/`
> directory was removed this session; historical code remains accessible via
> `git log -- src-tauri/`.

## Project Overview

**MBForge** is a desktop knowledge-work platform for molecular science and drug
discovery. It ingests scientific PDFs, extracts molecules and activities,
indexes them into a searchable knowledge base, and exposes an AI agent for
cross-document reasoning.

Pipeline: `PDF → classify → extract → segment → chunk → index → query`.

Stack:

- **Frontend**: React 19 + Vite 8 + TypeScript 6. Runs in the browser only.
  No Tauri shell.
- **Backend**: FastAPI on `127.0.0.1:18792`. Single Python process. `uvicorn
  mbforge.app:app`. 53 routes across 18 routers.
- **Agent**: LangGraph (`>=0.4.0`) + langchain 0.3+. 5 tools, multi-session,
  SSE streaming.
- **Models**: MolDetv2 (YOLO26n),
  MolScribe. Lazy-loaded on first call.

## Architecture & Data Flow

Five-layer split, top-down:

| Layer | Path | Responsibility |
|---|---|---|
| Frontend | `frontend/src/` | React components, routing, `AppContext` global state, `httpFetch` bridge |
| HTTP routers | `src/mbforge/routers/` | FastAPI route handlers; one file per resource |
| Core | `src/mbforge/core/` + `pipeline/` + `agent/` | Business logic, persistence, embeddings, pipeline stages |
| Backends | `src/mbforge/backends/` | Local model wrappers (moldet, molscribe) |
| Utils | `src/mbforge/utils/` + `models/` | Logger, config, helpers, Pydantic schemas |

**Data flow** (PDF in → query out):

1. Frontend uploads PDF via `POST /api/v1/documents/upload` → stored under `{project_root}/`.
2. `pipeline/runner.py` orchestrates 6 stages: classify → extract_text → extract_molecules → normalize → persist_molecules → chunk/index.
3. Stage outputs feed `core/knowledge_base.py` (SQLite business tables) and the OpenKB + PageIndex collection (vectorless tree reasoning + dense rerank).
4. Frontend queries via `GET /api/v1/kb/search` (PageIndex tree reasoning).
5. Agent chat streams via `GET /api/v1/agent/chat` (SSE, LangGraph nodes invoke `agent/tools.py`).

**Cross-boundary types**: `Document`, `Chunk`, `Molecule`, `AgentMessage` — all
serialized as JSON via Pydantic over HTTP. No IPC, no shared memory.

## Key Directories

```
MBForge/
├── frontend/                          React + Vite app
│   ├── src/
│   │   ├── api/
│   │   │   ├── http/                  HTTP bridge (httpFetch, isOnline)
│   │   │   └── sse.ts                 SSE streaming client
│   │   ├── components/                Page-level + ui/ atoms
│   │   ├── context/AppContext.tsx     Global state
│   │   ├── hooks/                     useTheme, useAnimations, useToast
│   │   └── utils/errors.ts            AppError + ErrorCode
│   └── index.html
├── src/mbforge/                       Python backend
│   ├── app.py                         App entry — 53 routes, 18 routers
│   ├── server.py                      Dev uvicorn target
│   ├── __main__.py                    `python -m mbforge`
│   ├── routers/                       18 FastAPI routers
│   ├── agent/                         LangGraph agent
│   ├── core/                          database, project, knowledge_base, semantic_cache, resource_manager
│   ├── pipeline/                      classify, extract_text, segment, chunk, index, runner
│   ├── backends/                      moldet, molscribe, moldet_v2_ft
│   ├── parsers/molecule/              coords, coref_alt
│   ├── chem/                          Cheminformatics utils
│   ├── models/                        Pydantic models (common, project)
│   └── utils/                         logger, config, helpers, constants
├── tests/                             Python tests (unit/, integration/)
├── docs/                              Specs, plans, references (see § Documentation)
├── TODO/INDEX.md                      Master task board
├── pyproject.toml                     uv + ruff + pytest
├── uv.lock
├── LICENSE                            CC BY-NC-SA 4.0
├── configs/                           YAML configs (constants, OCR)
├── assets/icon/                       Icon source files
└── assets/models/                     Dev model fixtures (gitignored)
```

## Development Commands

Run from `MBForge/`.

### Install

```bash
uv sync --dev                  # Python deps (uv, not pip)
npm --prefix frontend install   # Frontend deps
```

### Run (2 terminals)

```bash
# 1. Python backend (FastAPI on 127.0.0.1:18792)
uv run uvicorn mbforge.app:app --host 127.0.0.1 --port 18792

# 2. Frontend dev server (Vite proxies /api → 18792)
cd frontend && npm run dev
```

The Vite dev server runs on `:5173`. All `/api/*` calls proxy to the Python
backend — no CORS, no separate port in the frontend code.

### Compile / typecheck / lint

```bash
uv run ruff check src/                       # Python lint
uv run ruff format src/ --check              # Python format
cd frontend && npx tsc --noEmit              # TS strict mode
```

### Production build

```bash
cd frontend && npm run build                 # outputs frontend/dist
```

No desktop bundle step — the app is a web frontend + Python backend. Deploy
`frontend/dist/` and `src/mbforge/` together (or run both behind a reverse
proxy).

## Code Conventions & Common Patterns

### Python

- **Logger**: every module starts with `logger = get_logger(__name__)`. Never `print()`.
- **Errors**: inherit from `MBForgeError` (`src/mbforge/utils/helpers.py`) with `status_code` + `error_code` class attrs. FastAPI handler maps to `{success: false, error, error_code}`. No bare `except:`.
- **Async I/O**: wrap blocking calls with `await loop.run_in_executor(None, lambda: ...)` — `app.py` and `server.py` do this for model calls.
- **Type hints**: use `from __future__ import annotations` to avoid runtime forward refs. Public functions must be fully annotated.
- **Lint/format**: ruff (select E/F/I/N/W/UP/B/C4/SIM), `ruff format` at line-width 88.
- **Pydantic**: request/response models live in `src/mbforge/models/` (shared) or next to the router (local). Never use raw `dict` for API boundaries.
- **Naming**: `snake_case` for functions/vars, `PascalCase` for classes, `SCREAMING_SNAKE_CASE` for module constants. Booleans prefixed `is_`/`has_`/`can_`.

### TypeScript / React

- **Components**: `export default function ComponentName()` for page-level; `function SubComponent()` for local UI. Hooks prefixed `use`.
- **State**: local → `useState`; cross-component → props; global → `useAppContext()`. Persistent settings use `localStorage` with `mbforge_` prefix.
- **HTTP**: every backend call goes through `api/http/*.ts`. Pattern: `await httpFetch<T>('/api/v1/...', { method, body })` wrapped in shared error handling (see `_utils.ts`). SSE via `api/sse.ts`.
- **Animations**: import variants from `hooks/useAnimations.ts` (`fadeUp`, `scaleIn`, `staggerContainer`, …). Do not redefine `initial/animate/exit/transition` inline.
- **Imports**: `@/` alias for `frontend/src/`. Cross-directory imports MUST use `@/` (e.g. `from '@/hooks/useToast'`, never `'../../hooks/useToast'`). Same-directory imports MAY use `./` (e.g. `from './_utils'`). This makes files position-independent — moving a file never breaks its imports. `import type` for type-only imports; three groups (std → third-party → project) separated by blank lines.
- **Style**: prefer CSS variables (`var(--accent)`, `var(--bg-surface)`); inline `style` ≤ 3 props, otherwise extract. Verify dark mode for new styles.
- **TS strict**: `strict`, `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch` all on.

### Common patterns

- **Adding a REST endpoint**: define Pydantic request/response → handler in `routers/{name}.py` → wire into `app.py` (router list at top of file) → add `httpFetch` wrapper in `frontend/src/api/http/{name}.ts`.
- **Adding a Pydantic model**: place in `src/mbforge/models/` if shared, or inline if router-local. Re-export from `models/__init__.py`.
- **Adding an agent tool**: subclass `BaseTool` in `agent/tools.py` → register in tool list → update `agent/graph.py` system prompt if the tool needs discovery hints.

## Settings & Configuration

**Single source**: `mbforge.utils.config` exports the four allowed entry
points. Any code that reads or writes global config without going through
them is a bug.

### Calling settings from Python

```python
from mbforge.utils.config import (
    load_global_config,    # lru_cache, single read
    save_global_config,    # single write
    update_settings,       # partial update + validate + persist
    reset_settings,        # back to defaults
)
```

`load_global_config()` returns the cached `AppConfig`. Treat as read-only
— mutations won't persist unless routed through `update_settings()`.
`update_settings(partial)` does deep-merge → Pydantic validation →
persist; on `ValidationError` the router maps it to HTTP 422.

### Calling settings from a router

```python
from ..utils.config import update_settings, reset_settings

@router.put("")
async def settings_update(body: dict[str, Any]) -> dict:
    try:
        new_cfg = update_settings(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    return {"success": True, "settings": new_cfg.model_dump()}
```

Never inline `deep_merge` + `model_validate` + `save_global_config` —
the helpers handle cache invalidation and Pydantic error mapping.

### Adding a new field

1. Add to `AppConfig` (or a nested `BaseModel` like `LLMConfig`).
2. Provide a default — Pydantic 2 with `extra="ignore"` tolerates
   missing/extra fields, so existing `settings.json` files won't crash
   on first load.
3. If env-overridable, use `Field(..., validation_alias=...)` or rely on
   the existing `env_prefix="MBFORGE_"` wiring on `AppConfig`.
4. Add a test in `tests/unit/test_config.py`.

### Adding a new endpoint

`POST /api/v1/settings/reset` is the template: thin router, helper does
the work. Never write to disk from a router.

### Frontend

`@/api/http/settings` exports `getSettings()` / `saveSettings(partial)`.
The `RecentProject` type must match the backend Pydantic schema
(`{root, name}`). Use `root`, never `path`.

### Migration gotchas

If you change a field name or type, existing `settings.json` files on
disk may fail to deserialize. Either (a) keep a default that the old
value maps onto, or (b) extend `_migrate_legacy_configs()` with a
one-shot transform.

## Important Files

| File | Role |
|---|---|
| `src/mbforge/app.py` | App entry — registers all 18 routers, exception handlers, lifespan |
| `src/mbforge/server.py` | Dev uvicorn target (lazy prewarm) |
| `src/mbforge/__main__.py` | `python -m mbforge` → uvicorn on 18792 |
| `src/mbforge/agent/graph.py` | LangGraph agent graph definition |
| `src/mbforge/agent/tools.py` | 5 agent tools (KB search, molecule search, doc fetch, notes, settings) |
| `src/mbforge/pipeline/runner.py` | 6-stage pipeline orchestrator (Phase 1: extract_molecules added) |
| `src/mbforge/core/database.py` | SQLite business tables + connection pool |
| `src/mbforge/core/knowledge_base.py` | KB CRUD + RRF fusion logic |
| `src/mbforge/openkb/` | OpenKB + PageIndex adapter (vectorless tree reasoning + dense rerank) |
| `src/mbforge/backends/moldet_v2_ft.py` | Fine-tuned YOLO26n MolDet backend (alternative to default). |
| `src/mbforge/utils/helpers.py` | `MBForgeError` + 7 subclasses + `run_sync` |
| `src/mbforge/utils/logger.py` | `get_logger` + `setup_logging` |
| `frontend/src/api/http/_utils.ts` | `httpFetch` wrapper + error normalization |
| `frontend/src/api/sse.ts` | SSE streaming client |
| `frontend/src/utils/errors.ts` | `AppError` + `ErrorCode` enum |
| `frontend/src/main.tsx` | React 19 root, BrowserRouter, App |
| `frontend/src/context/AppContext.tsx` | Global state |
| `pyproject.toml` | uv + ruff + pytest config, langchain/langgraph deps |
| `uv.lock` | Python lock |

**Configuration precedence** (highest → lowest):
1. `MBFORGE_*` env vars
2. `~/.config/MBForge/config.json` (Settings UI writes here)
3. Built-in defaults

**Storage locations** (per project): `{root}/.mbforge/knowledge_base.db` (SQLite),
OpenKB PageIndex collection managed under `openkb/`, per-project
semantic cache. Global config: `~/.config/MBForge/config.json` (Linux) /
`%APPDATA%\MBForge\config\config.json` (Windows).

## Runtime & Tooling Preferences

| Tool | Choice | Notes |
|---|---|---|
| Python package manager | **uv** (NOT pip) | `uv sync --dev`, `uv run` for execution |
| Python venv | `.venv` at project root | `uv venv` |
| Frontend | **npm** (NOT pnpm/bun/yarn) | `package-lock.json` is the lock |
| Node version | >=20.19 or >=22.12 (Vite 8 baseline) | No `.nvmrc` |
| Lint/format (Python) | ruff (E/F/I/N/W/UP/B/C4/SIM) | `ruff format` at width 88 |
| Lint/format (TS) | eslint + typescript-eslint `strictTypeChecked` | Run via `npm run lint` |
| GPU | CUDA 12.8 (PyTorch wheel index `pytorch-cu128`) | Required only for `moldet`/`molscribe`; LLM/embed run on CPU |
| HTTP timeouts | `httpx.AsyncClient` per backend, configured in `backends/*.py` | No shared singleton needed |

**.env template**: see `.env.template` (root). Variables:
`MBFORGE_LLM_*`, `MBFORGE_EMBED_*`, `MBFORGE_RERANK_*`, `HF_HOME`, `MODELSCOPE_CACHE`, `TORCH_HOME`.

## Testing & QA

### Frameworks

- **Python**: pytest. `pyproject.toml` sets `testpaths = ["tests"]`. Layout:
  `tests/unit/parsers/test_coref_alt.py` (only currently populated unit test),
  `tests/integration/` for end-to-end.
- **Frontend**: vitest 4 + jsdom + `@testing-library/jest-dom`
  (via `frontend/src/test/setup.ts`). Tests live alongside source as
  `*.test.{ts,tsx}`. Coverage via `@vitest/coverage-v8`.

### Running tests

```bash
# Python
uv run pytest tests/ -v

# Python with coverage
uv run pytest tests/ --cov=src/mbforge --cov-report=term-missing

# Frontend
cd frontend && npm run test                     # vitest run
cd frontend && npm run test:ui                  # vitest with UI
cd frontend && npm run test -- --coverage       # v8 coverage
```

### Conventions

- **Test names**: `test_{feature}_{scenario}` (e.g. `test_classify_pdf_returns_paper`).
- **Test intent**: assertions express *why* the behavior matters, not just *what* it does. Tests that pass when business logic is wrong are design failures.
- **No mocks of real systems**: use `tmp_path` for FS, real SQLite in `:memory:`, real OpenKB test collection.
- **Coverage goal**: ≥70% on core logic per `TODO/INDEX.md` P1 items.

## Documentation

| Doc | Location | Audience |
|---|---|---|
| Project entry | [README.md](README.md) | Human users — quick start, features, architecture |
| Repo guidelines | [AGENTS.md](AGENTS.md) | AI coding assistants |
| AI quick-ref | [CLAUDE.md](CLAUDE.md) | Repository-level AI context |
| Task board | [TODO/INDEX.md](TODO/INDEX.md) | Prioritized work (P0–P3) |
| Specs | [docs/specs/](docs/specs/) | Architecture, code style, molecule representation |
| References | [docs/REFERENCES.md](docs/REFERENCES.md) | Open-source attribution |

---

**## Commit Granularity — 一主题 = 一 commit

**Don't split commits by file — split by logical change.** A single
feature/refactor/bug fix commits as one atomic unit even if it spans
15 files; sub-tasks are described in the commit body, not broken into
separate commits.

Use the commit body (Markdown) to:

- State the **why** (background, motivation, scope)
- List **what changed** (file groups, sub-tasks as `- [ ]` checklists)
- Note **breaking changes** and **migration steps**
- Describe **how to verify** and **how to roll back**

**Split into separate commits**: unrelated chores, distinct features,
version bumps, independent bug fixes.
**Merge into one commit**: every file involved in a single refactor,
every layer (backend + frontend + docs) of one feature, every step of
one cleanup campaign.

Anti-pattern:
```
chore: rename project_root → library_root in app.py
chore: rename project_root → library_root in pipeline.py
chore: rename project_root → library_root in knowledge_base.py
```

Correct:
```
refactor(core): migrate project management to unified library

- [ ] backend: app.py swap project router → library router
- [ ] backend: rename project_root → library_root across callers
- [ ] backend: replace index.json scan with LibraryStore queries
- [ ] frontend: GroupsPanel + RecentProjectsSection update
- [ ] delete dead project router / core.project / models.project
```

---

**Don't see what you need?** Check `TODO/INDEX.md` for known gaps, or grep the
codebase — it's a small, well-organized Python project.