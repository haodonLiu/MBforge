# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Last sync**: 2026-07-05. Head migrated off the Rust/Tauri workspace
> (`commit 4b70ae8`); KB backend swapped to OpenKB + PageIndex
> (`4fbde55`); Phase 1 molecule extraction landed
> (`extract_molecules.py` → `normalize.py` → `persist_molecules.py`); the
> legacy `src-tauri/` directory was removed this session (history is
> still in git via `git log -- src-tauri/`).
> If reality drifts from this file, **the code wins**; update this file in the
> same PR. Detailed conventions live in [AGENTS.md](./AGENTS.md) — don't
> duplicate them here.

---

## 1. What MBForge Is

Desktop knowledge-work platform for molecular science / drug discovery.
PDFs in → structured molecules + activities → searchable knowledge base →
LangGraph agent chat.

```
PDF → classify → extract → segment → chunk → index → query
                                ↓
                       knowledge base (SQLite + OpenKB)
                                ↓
                       agent chat + molecule ops (FastAPI)
```

Two frontends share the same backend:

- **Web** (`frontend/`) — React 19 + Vite 8 + TS 6, dev server `:5173`, proxies `/api/*` → `127.0.0.1:18792`.
- **Native** (`src/mbforge/gui/`) — Dear PyGui 2.0 desktop shell, talks to the same FastAPI over loopback.

---

## 2. Common Commands

```bash
# Install
uv sync --dev                          # Python deps
npm --prefix frontend install          # Frontend deps

# Run — pick one
uv run uvicorn mbforge.app:app --host 127.0.0.1 --port 18792   # backend only
python start.py                                                    # backend + frontend (auto-open browser)
cd frontend && npm run dev                                         # frontend only

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
cd frontend && npm run test                                # vitest run

# Production build
cd frontend && npm run build                              # → frontend/dist (mounted by FastAPI)
```

RTK-friendly equivalents: prefix dev commands with `rtk` when possible (e.g. `rtk pytest`); for git use `rtk git status` etc.

Tooling pins (see `pyproject.toml`): **uv** (not pip), **npm** (not pnpm/yarn/bun), ruff (E/F/I/N/W/UP/B/C4/SIM, width 88), Node ≥20.19/22.12 (Vite 8 baseline).

---

## 3. Repository Layout (top-level only)

| Path | Purpose |
|---|---|
| `src/mbforge/` | Python backend package (FastAPI app, routers, agent, pipeline, core, backends, parsers, chem, models, utils, gui, openkb) |
| `src/mbforge/app.py` | FastAPI factory — registers **18 routers** under `/api/v1/*`, mounts `frontend/dist/` if present |
| `src/mbforge/server.py` | Dev uvicorn target for the local-model sidecar (mounted at `/api/v1/models`) |
| `src/mbforge/gui/` | Dear PyGui native frontend (alternative to `frontend/`) |
| `frontend/` | React + Vite web frontend |
| `tests/` | pytest (`tests/unit/`, `tests/integration/`) + vitest (`frontend/src/**/*.test.ts*`) |
| `docs/specs/` | Architecture conventions, code style, E-SMILES, MoleCode, molecule representation |
| `configs/` | YAML configs (constants, OCR) |
| `assets/{icon,models}/` | Icon sources; dev model fixtures (gitignored) |
| `TODO/INDEX.md` | Master task board (P0–P3) — the only TODO file |

For deeper module breakdown of `src/mbforge/`, see [AGENTS.md § Key Directories](./AGENTS.md#key-directories).

---

## 4. Architecture — The Big Picture

**Five-layer split** (top → bottom):

```
Frontend (React or Dear PyGui)
    ↓ HTTP / SSE          (httpFetch / sse.ts  or  gui/api/client.py)
Routers (FastAPI, 18 files in src/mbforge/routers/)
    ↓
Core + Agent + Pipeline  (src/mbforge/{core,agent,pipeline}/)
    ↓
Backends (src/mbforge/backends/)  ←── lazy-loaded ML models
    ↓
SQLite + OpenKB + filesystem   (per-project .mbforge/)
```

**Central data flow (PDF in → answer out):**

1. Frontend uploads PDF via `POST /api/v1/documents/upload` → project-local storage.
2. `pipeline/runner.py` runs **6 stages** now (Phase 1 added molecule extraction):
   classify → `extract_text` → `extract_molecules` → `normalize` → `persist_molecules` → `chunk`/`index`.
   Each stage writes intermediate state to the SQLite business tables
   (`core/database.py`) plus the OpenKB index.
3. Frontend queries via `GET /api/v1/kb/search` (PageIndex tree reasoning + dense rerank).
4. Agent chat streams via `GET /api/v1/agent/chat` (SSE; LangGraph nodes invoke tools in `agent/tools.py`).

**Lazy-loaded model backends** (no prewarm except OpenKB): `moldet` (YOLO26n), `molscribe` (Swin + TR). First request per backend pays 5–30 s load cost — see `TODO/INDEX.md` C-4.

**Storage locations:**
- Per-project: `{root}/.mbforge/knowledge_base.db` + the OpenKB + PageIndex collection under `openkb/`.
- Global config: `~/.config/MBForge/config.json` (Linux) / `%APPDATA%\MBForge\config\config.json` (Windows). Precedence: `MBFORGE_*` env vars > global config > defaults.

---

## 5. Where to Read Next

| Need | Doc |
|---|---|
| Conventions (Python, TS, error types, naming) | [AGENTS.md](./AGENTS.md) |
| Prioritized work, known gaps | [TODO/INDEX.md](./TODO/INDEX.md) |
| Human-facing quick start / architecture diagram | [README.md](./README.md) |
| Module boundaries, layering rules | [docs/specs/architecture-conventions.md](./docs/specs/architecture-conventions.md) |
| SMILES / E-SMILES / MoleCode layering | [docs/specs/molecular-representation.md](./docs/specs/molecular-representation.md) |
| Code style (full) | [docs/specs/code-style.md](./docs/specs/code-style.md) |

**Before touching code, consult AGENTS.md.** It is the canonical manual for AI
contributors and covers: dev commands, conventions, REST/agent-tool workflows,
testing rules, and the testing-intent criterion (tests verify *why*, not just
*what*).

Commit convention (from README, also used in CI scopes):

```
<type>(<scope>): <subject>
types:   feat | fix | refactor | perf | test | docs | chore
scopes:  frontend | python | api | router | pipeline | agent | backend | deps
```
