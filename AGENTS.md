# Repository Guidelines

> Practical guide for AI assistants working on MBForge. Covers architecture,
> conventions, and the day-to-day commands needed to add a feature, fix a bug,
> or run tests.

> **Snapshot**: 2026-07-09 — Python-only backend. The legacy `src-tauri/`
> directory was removed (see `git log -- src-tauri/`). Pipeline still
> 9 stages; OCR cloud-first fallback chain (MinerU → PaddleOCR → GLMOCR
> → RapidOCR). **2026-07-08 MolDetv2-FT migration**: legacy Doc+General
> MolDet pair replaced by a single fine-tuned YOLO26n model that
> jointly detects molecules and coref identifier bboxes in one
> inference. See `docs/superpowers/plans/2026-07-08-text-reorg-molecode.md`
> for the migration plan and `routers/coref.py` for the FT-driven
> coref bridge.

## Project Overview

**MBForge** is a desktop knowledge-work platform for molecular science and drug
discovery. It ingests scientific PDFs, extracts molecules and activities,
indexes them into a searchable knowledge base, and exposes an AI agent for
cross-document reasoning.

Pipeline: `PDF → extract → density → rough_md → detect → insert_molecode → reorganize → pageindex → wiki → persist_mols → register_links → persist → query`.

Stack:

- **Frontend**: React 19 + Vite 8 + TypeScript 6. Runs in the browser only.
  No Tauri shell.
- **Backend**: FastAPI on `127.0.0.1:18792`. Single Python process. `uvicorn
  mbforge.app:app`. 19 routers registered.
- **Models**: MolDetv2-FT (YOLO26n, fine-tuned for joint molecule + coref
  identifier detection in one inference), MolScribe, OCR fallback chain
  (MinerU → PaddleOCR → GLMOCR → RapidOCR, cloud-first with local
  fallback). All lazy-loaded on first call. The legacy Doc + General
  MolDet pair (moldet.py) was removed in the 2026-07-08 migration; the
  new main pipeline is `backends/moldet_v2_ft.py:MolDetv2FTDetector` +
  `routers/moldet_api.py:/extract-pdf-page` (PDF → FT detect → coref pair
  → MolScribe → SMILES + bbox + pairs).

## Architecture & Data Flow

Five-layer split, top-down:

| Layer | Path | Responsibility |
|---|---|---|
| Frontend | `frontend/src/` | React components, routing, `AppContext` global state, `httpFetch` bridge |
| HTTP routers | `src/mbforge/routers/` | FastAPI route handlers; one file per resource |
| Core | `src/mbforge/core/` + `pipeline/` + `agent/` | Business logic, persistence, embeddings, pipeline stages |
| Backends | `src/mbforge/backends/` | Local model wrappers (moldet_v2_ft, molscribe, ocr) |
| Utils | `src/mbforge/utils/` + `models/` | Logger, config, helpers, Pydantic schemas |

**Data flow** (PDF in → query out):

1. Frontend uploads PDF via `POST /api/v1/documents/upload` → stored under `{library_root}/`.
2. `pipeline/runner.py` orchestrates 9 stages: extract (PDF text + OCR fallback) → density → rough_md → detect (MolDetv2-FT joint detection + MolScribe) → insert_molecode → reorganize (LLM semantic reorg) → pageindex → wiki → persist_mols → register_links → persist. The `detect` stage uses `pipeline/extract_molecules.py:extract_molecules_from_pdf` which runs FT detection + coref pairing + MolScribe per-mol-bbox OCR (see `routers/moldet_api.py:/extract-pdf-page` for the equivalent HTTP endpoint).
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
│   ├── app.py                         App entry — 19 routers
│   ├── server.py                      Dev uvicorn target
│   ├── __main__.py                    `python -m mbforge`
│   ├── routers/                       19 FastAPI routers
│   ├── agent/                         LangGraph agent
│   ├── core/                          database, library, knowledge_base, semantic_cache, resource_manager
│   ├── pipeline/                      classify, extract_text, segment, chunk, index, runner, organizer
│   ├── backends/                      molscribe, moldet_v2_ft, ocr/ (chain, mineru, paddleocr, glmocr, rapidocr_adapter)
│   ├── parsers/molecule/              coords, coref_alt
│   ├── chem/                          Cheminformatics utils
│   ├── models/                        Pydantic models (common, library, molecule)
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
| `src/mbforge/app.py` | App entry — registers all 19 routers, exception handlers, lifespan |
| `src/mbforge/server.py` | Dev uvicorn target (lazy prewarm) |
| `src/mbforge/__main__.py` | `python -m mbforge` → uvicorn on 18792 |
| `src/mbforge/agent/graph.py` | LangGraph agent graph definition |
| `src/mbforge/agent/tools.py` | 5 agent tools (KB search, molecule search, doc fetch, notes, settings) |
| `src/mbforge/pipeline/runner.py` | 9-stage pipeline orchestrator (extract → density → rough_md → detect → insert_molecode → reorganize → pageindex → wiki → persist_mols → register_links → persist) |
| `src/mbforge/core/database.py` | SQLite business tables + connection pool |
| `src/mbforge/core/knowledge_base.py` | KB CRUD + RRF fusion logic |
| `src/mbforge/openkb/` | OpenKB + PageIndex adapter (vectorless tree reasoning + dense rerank) |
| `src/mbforge/backends/moldet_v2_ft.py` | **The** MolDet backend (FT detector). YOLO26n fine-tuned for joint molecule + coref identifier detection in one inference. |
| `src/mbforge/backends/ocr/rapidocr_adapter.py` | Crop-level RapidOCR adapter with `ThreadPoolExecutor` batch recognition. Used by `routers/coref.py` to OCR the FT-detected label bboxes. Uses `use_det=False` to skip detection (crops are pre-bounded by FT). |
| `src/mbforge/parsers/molecule/coref_alt.py` | Coref KB-shape bridge: `CorefBbox` / `CorefResult` dataclasses, `_pair_corefs` (geometry-based pairing), `coref_to_rust_dict` (Rust vlm_chem bridge), `detect_coref_via_ft_detector` (single entry point for the FT pipeline). |
| `src/mbforge/routers/coref.py` | Coref HTTP bridge: `POST /api/v1/coref/figure-labels` + `POST /api/v1/coref/predictions`. Renders the page, runs FT detect, batch-OCR's label bboxes, returns KB-shaped `FigureLabel[]` / `CorefPrediction[]` with real text (or synthetic fallback). 30s per-page cache. |
| `src/mbforge/backends/ocr/__init__.py` | OCR backend registry — lazy import + factory |
| `src/mbforge/backends/ocr/chain.py` | Fallback chain: MinerU → PaddleOCR → GLMOCR → RapidOCR |
| `src/mbforge/backends/ocr/mineru.py` | MinerU OCR wrapper (cloud), tried first |
| `src/mbforge/backends/ocr/paddleocr.py` | PaddleOCR wrapper |
| `src/mbforge/backends/ocr/glmocr.py` | GLMOCR wrapper |
| `src/mbforge/routers/ocr.py` | OCR config + status endpoints |
| `src/mbforge/utils/helpers.py` | `MBForgeError` + 8 subclasses + `run_sync` + `http_status_to_severity` |
| `src/mbforge/utils/logger.py` | `get_logger` + `setup_logging(json_mode=)` + `JsonFormatter` + `DiagnosticRingHandler` + ring-buffer helpers |
| `src/mbforge/routers/diagnostics.py` | `/api/v1/diagnostics/{errors,stats}` — unified error ring buffer + front-end error ingestion |
| `frontend/src/api/http/_utils.ts` | `httpFetch` (extracts `error_code`/`severity`/`category` from backend JSON body) + `invokeWithError` + `registerGlobalErrorHandlers` |
| `frontend/src/api/sse.ts` | SSE streaming client |
| `frontend/src/utils/errors.ts` | `AppError` + `ErrorCode` + `Severity` enums + `severityFromHttpStatus` + `toAppError` |
| `frontend/src/hooks/useErrorReport.ts` | Debounced (1.5 s) `keepalive` POST of `ErrorBoundary` caught errors to `/api/v1/diagnostics/errors` |
| `frontend/src/components/ErrorBoundary.tsx` | Wraps `<AppRoutes />`; `componentDidCatch` reports to backend + retains copy/refesh UX |
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
  `tests/unit/` for unit tests. After 2026-07-08 the active unit test
  files include `tests/unit/test_rapidocr_adapter.py` (14 tests,
  crop-level RapidOCR with ThreadPoolExecutor batch) and
  `tests/unit/test_coref_ocr_integration.py` (7 tests, FT →
  coref → OCR KB-shape bridge) for the coref path, plus the legacy
  smoke tests under `tests/unit/test_routers_smoke.py` and friends.
  Note: `tests/unit/parsers/test_coref_alt.py` and
  `tests/unit/parsers/test_molecule_parsers.py` were removed in the
  2026-07-08 FT migration (they tested removed MolDetv2DocDetector).
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