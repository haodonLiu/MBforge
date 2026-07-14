# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Last sync**: 2026-07-14. Refresh against live tree: routers registered
> in `app.py` via `include_router` only (**no** nested model_server Mount —
> molscribe/models/pdf-render hang on main app with correct prefixes).
> Unified storage `{library_root}/.mbforge/library.db`. Entry:
> `python -m mbforge` or uvicorn. Pipeline: **7 modular stages**. Frontend:
> React 19 + Vite 8 + React Query. If reality drifts, **the code wins**.
> Detailed conventions: [AGENTS.md](./AGENTS.md).

---

## 1. What MBForge Is

Desktop knowledge-work platform for molecular science / drug discovery.
PDFs in → structured molecules + activities → searchable knowledge base →
LangGraph agent chat.

```
PDF → pipeline (7 modular stages) → knowledge base (SQLite + OpenKB) → agent chat + molecule ops (FastAPI)
```

Frontend:

- **Web** (`frontend/`) — React 19 + Vite 8 + TS 6, dev server `:5173`, proxies `/api/*` → `127.0.0.1:18792`. Only official UI (Dear PyGui / Tauri removed).

Stack pins: **Python 3.12 only** (`requires-python = ">=3.12,<3.13"`), **uv** (not pip), **npm** (not pnpm/yarn/bun), Node ≥20.19/22.12 (Vite 8).

---

## 2. Common Commands

```bash
# Install
uv sync --dev                          # Python deps (+ dev group)
npm --prefix frontend install          # Frontend deps

# Run — pick one
uv run uvicorn mbforge.app:app --host 127.0.0.1 --port 18792   # backend only
python -m mbforge --dev                # same, optional auto-open browser
cd frontend && npm run dev             # frontend only (:5173 → proxy /api)
cd frontend && npm run dev:all         # backend + frontend via concurrently

# Single Python test (by name substring)
uv run pytest tests/ -v -k "<substring>"
# All Python tests
uv run pytest tests/ -v
# Python tests with coverage
uv run pytest tests/ --cov=src/mbforge --cov-report=term-missing

# Lint / typecheck / format
uv run ruff check src/
uv run ruff format src/ --check
cd frontend && npx tsc --noEmit
cd frontend && npm run lint
cd frontend && npm run test            # vitest run (not watch)

# Production build
cd frontend && npm run build           # → frontend/dist (mounted by FastAPI if present)
```

Migrations / ops (when needed):

```bash
uv run python -m mbforge.migrate-library <library_root>
uv run python scripts/migrate_artifact_paths.py
```

RTK-friendly: prefix with `rtk` when available (`rtk pytest`, `rtk git status`).

Port hygiene: default backend `18792`, Vite `5173`. AI assistants must free these ports after verification — prefer ephemeral ports for temp runs.

---

## 3. Repository Layout (top-level only)

| Path | Purpose |
|---|---|
| `src/mbforge/` | Python backend (FastAPI app, routers, agent, pipeline, core, backends, parsers, chem, models, utils, openkb) |
| `src/mbforge/app.py` | FastAPI factory — all `/api/v1/*` routers + optional `frontend/dist/` |
| `src/mbforge/core/artifact.py` | `ArtifactResolver` — sole authority for paths under `{library_root}/storage/` |
| `src/mbforge/core/layout.py` | `LibraryLayout` — library-level path helpers |
| `src/mbforge/server.py` | Optional standalone model sidecar (`uvicorn mbforge.server:app`) — not mounted into main app |
| `frontend/` | React 19 + Vite 8 UI. Server state via `@tanstack/react-query` (`api/query/`); HTTP in `api/http/`; SSE in `api/sse.ts` + `api/http/sse.ts` |
| `tests/` | pytest: `tests/unit/` (agent, backends, core, openkb, parsers, pipeline, routers) + `tests/integration/` |
| `scripts/` | install/docker helpers, path/openkb migrations, smoke scripts |
| `docs/specs/` | Architecture conventions, code style, E-SMILES, MoleCode, molecule representation |
| `docs/architecture/` | Error/logging, pipeline stage reference |
| `assets/{icon,models}/` | Icon sources; dev model fixtures (gitignored) |
| `TODO/INDEX.md` | Master task board (P0–P3) — the only TODO file |

Deeper module map: [AGENTS.md § Key Directories](./AGENTS.md#key-directories).

---

## 4. Architecture — The Big Picture

**Five-layer split** (top → bottom):

```
Frontend (React 19 + Vite)
    ↓ HTTP / SSE          (api/http/* + React Query hooks; SSE via sse clients)
Routers (FastAPI include_router only — no nested model_server Mount)
    ↓
Core + Agent + Pipeline  (src/mbforge/{core,agent,pipeline,openkb}/)
    ↓
Backends (src/mbforge/backends/)  ←── lazy-loaded ML models
    ↓
SQLite + OpenKB + filesystem   (per-library .mbforge/ + storage/)
```

**Routers registered in `app.py`** (all `include_router`, correct prefixes):

`library`, `documents`, `pipeline`, `kb`, `molecule`, `agent`, `chem`, `coref`,
`detection-cache`, `notes`, `settings`, `text`/`health`/`resource` (prefix
`/api/v1`), `events`, `pdf`, `sar`, `ocr`, `diagnostics`, `moldet`,
`molscribe` (`/api/v1/molscribe`), `models` (`/api/v1/models` — test +
`mol/render`), `pdf_render` (`/api/v1/pdf/render-pages`, …).
Standalone sidecar: `mbforge.server:app` only when run alone.

**Central data flow (PDF in → answer out):**

1. Frontend uploads PDF via `POST /api/v1/documents/upload` → library-local storage.
2. `pipeline/runner.py` orchestrates **7 modular stages** in `pipeline/stages/*.py`,
   state in `pipeline/context.py:PipelineContext`, contract
   `pipeline/stages/base.py:StageExecutor` → `StageResult`:
   - **Extract** — PDF text + OCR fallback chain
   - **Density** — classify text / mixed / image
   - **Markdown** — rough_md + MolDetv2-FT + MolScribe + MoleCode blocks
     (`pipeline/extract_molecules.py`; HTTP twin: `routers/moldet_api.py`)
   - **Reorganize** — LLM semantic reorg + optional MinerU-Popo
   - **Activity** — IC50 / Ki / EC50 / Kd from tables
   - **Index** — PageIndex tree + Wiki compilation (OpenKB)
   - **Persist** — persist_mols + register_links + persist_doc (cross-DB txn)
3. Query via `GET /api/v1/kb/search` (PageIndex tree + dense rerank).
4. Agent chat streams via agent router SSE (LangGraph + `agent/tools.py`).

**Active model stack** (lazy-loaded; first hit 5–30 s):

- Detector: `backends/moldet_v2_ft.py` (YOLO26n FT — joint molecule + coref label bboxes).
  `backends/moldet.py` is a **compat shim only** — do not import for new code.
- Recognizer: MolScribe (Swin + TR).
- OCR chain: MinerU → PaddleOCR → GLMOCR → RapidOCR (`backends/ocr/chain.py`).
  Crop OCR for coref labels: `rapidocr_adapter` (`use_det=False`).

**Storage** (`library_root` defaults to `~/MBForge`; settings/logs stay there even
if library root is moved):

- `{root}/.mbforge/library.db` — unified SQLite (docs, molecules, evidence, coref, queue, FTS5, …)
- `{root}/.mbforge/openkb/` — OpenKB + PageIndex collection
- `{root}/storage/{doc_id}/` — `source.pdf`, `reorganized.md`, `crops/`, `pages/` via `ArtifactResolver`
- Legacy crops `{root}/.mbforge/crops/` — read-only fallback until `scripts/migrate_artifact_paths.py`
- Global config: `~/MBForge/settings.json` only for business settings.
  `MBFORGE_*` = infra (host, log level, force-CPU) — does **not** override `AppConfig`.

**Config entry points** (only these): `load_global_config` / `save_global_config` /
`update_settings` / `reset_settings` in `mbforge.utils.config`. Field name is
`library_root` / `libraryRoot` — no `project_root` aliases.

**Frontend shape (high level):**

- Layout: `components/app/AppShell.tsx` + `LibraryBootstrap.tsx`
- Server state: `api/query/hooks/*` + `useIngestSSE` into React Query cache
- HTTP: always through `api/http/*` (`httpFetch`); prefer query hooks over raw calls
- Global UI state: `context/AppContext.tsx`; errors: `utils/errors.ts` + `ErrorBoundary`

---

## 5. Where to Read Next

| Need | Doc |
|---|---|
| Doc map (living vs historical) | [docs/README.md](./docs/README.md) |
| Conventions (Python, TS, config, paths) | [AGENTS.md](./AGENTS.md) |
| Prioritized work | [TODO/INDEX.md](./TODO/INDEX.md) |
| Human quick start | [README.md](./README.md) |
| Contrib flow | [CONTRIBUTING.md](./CONTRIBUTING.md) |
| Module boundaries | [docs/specs/architecture-conventions.md](./docs/specs/architecture-conventions.md) |
| Pipeline stages | [docs/architecture/pipeline-stages.md](./docs/architecture/pipeline-stages.md) |
| SMILES / E-SMILES / MoleCode | [docs/specs/molecular-representation.md](./docs/specs/molecular-representation.md) |
| Code style | [docs/specs/code-style.md](./docs/specs/code-style.md) |
| Error & logging | [docs/architecture/error-logging.md](./docs/architecture/error-logging.md) |
| Doc refresh rules | [.claude/documentation-governance.md](./.claude/documentation-governance.md) |
| Branches / SemVer | [docs/VERSION_CONTROL.md](./docs/VERSION_CONTROL.md) |

**Before touching code, consult AGENTS.md.** Canonical for AI contributors:
commands, REST/agent-tool workflows, testing-intent (tests verify *why*, not
just *what*), worktree hygiene, port hygiene.

Commit convention:

```
<type>(<scope>): <subject>
types:   feat | fix | refactor | perf | test | docs | chore
scopes:  frontend | python | api | router | pipeline | agent | backend | deps
```

### Commit Granularity — 一主题 = 一 commit

**不要按文件拆 commit，按主题拆。** 一个 feature / refactor / bug fix
即使横跨 15 个文件，仍作为一个原子 commit；子步骤写在 body（Markdown `- [ ]`），
不拆成多个小 commit。

Body 写清：

- **Why** — 背景、动机、影响范围
- **What** — 文件分组 + 子任务清单
- **Breaking changes** — API/字段重命名、迁移步骤
- **Verify** — 命令、测试名
- **Rollback** — revert 方式

**应拆**：无关 chore、独立 feature、版本 bump、独立 bug 修复。
**应合**：单次 refactor 全文件、单 feature 前后端 + 文档、一次清理活动。

反例：
```
chore: rename project_root → library_root in app.py
chore: rename project_root → library_root in pipeline.py
```

正例：
```
refactor(core): migrate project management to unified library

- [ ] backend: app.py swap project router → library router
- [ ] backend: rename project_root → library_root across callers
- [ ] frontend: GroupsPanel + RecentProjectsSection update
- [ ] delete dead project router / core.project / models.project
```
