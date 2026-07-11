# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Last sync**: 2026-07-11. Evidence-Linked Molecular Infrastructure Phase 1
> complete: `evidence` table added (schema v3→v4 migration), `ArtifactResolver`
> for unified path management (`storage/{doc_id}/crops/` replaces legacy
> `.mbforge/crops/`), frontend `EvidencePanel` shows molecule provenance with
> "打开原文" button. Migration script `scripts/migrate_artifact_paths.py` moves
> legacy crops to canonical location. **Pipeline refactored to 7 modular stages**
> (`pipeline/context.py` + `pipeline/stages/*.py` + `StageExecutor` protocol);
> `pipeline/runner.py` now only orchestrates. 19 routers total. If reality
> drifts from this file, **the code wins**; update this file in the same PR.
> Detailed conventions live in [AGENTS.md](./AGENTS.md) — don't duplicate them
> here.

---

## 1. What MBForge Is

Desktop knowledge-work platform for molecular science / drug discovery.
PDFs in → structured molecules + activities → searchable knowledge base →
LangGraph agent chat.

```
PDF → pipeline (7 modular stages) → knowledge base (SQLite + OpenKB) → agent chat + molecule ops (FastAPI)
```

Frontend:

- **Web** (`frontend/`) — React 19 + Vite 8 + TS 6, dev server `:5173`, proxies `/api/*` → `127.0.0.1:18792`. This is the only official UI; the legacy Dear PyGui shell was removed on 2026-07-10.

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
| `src/mbforge/` | Python backend package (FastAPI app, routers, agent, pipeline, core, backends, parsers, chem, models, utils, openkb) |
| `src/mbforge/app.py` | FastAPI factory — registers **19 routers** under `/api/v1/*`, mounts `frontend/dist/` if present |
| `src/mbforge/core/artifact.py` | `ArtifactResolver` — single authority for paths under `{library_root}/storage/` (prevents path traversal) |
| `src/mbforge/server.py` | Dev uvicorn target for the local-model sidecar (mounted at `/api/v1/models`) |
| `frontend/` | React 19 + Vite 8 web frontend — the only official UI |
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
Frontend (React 19 + Vite)
    ↓ HTTP / SSE          (httpFetch / sse.ts)
Routers (FastAPI, 19 files in src/mbforge/routers/)
    ↓
Core + Agent + Pipeline  (src/mbforge/{core,agent,pipeline}/)
    ↓
Backends (src/mbforge/backends/)  ←── lazy-loaded ML models
    ↓
SQLite + OpenKB + filesystem   (per-project .mbforge/)
```

**Central data flow (PDF in → answer out):**

1. Frontend uploads PDF via `POST /api/v1/documents/upload` → library-local storage.
2. `pipeline/runner.py` orchestrates **7 modular stages** defined in
   `pipeline/stages/*.py` and sharing state through `pipeline/context.py:PipelineContext`:
   - **Extract** (`ExtractStage`) — PDF text + OCR fallback
   - **Density** (`DensityStage`) — classify text/mixed/image
   - **Markdown** (`MarkdownStage`) — rough_md + detect molecules (MolDetv2-FT +
     MolScribe) + insert MoleCode blocks
   - **Reorganize** (`ReorganizeStage`) — LLM semantic reorg + optional MinerU-Popo
   - **Activity** (`ActivityStage`) — extract IC50/Ki/EC50/Kd from tables
   - **Index** (`IndexStage`) — PageIndex tree + Wiki compilation
   - **Persist** (`PersistStage`) — persist_mols + register_links + persist_doc in one
     cross-database transaction
   Each stage implements the `StageExecutor` protocol and writes intermediate state
   to the SQLite business tables (`core/database.py`) plus the OpenKB index.
3. Frontend queries via `GET /api/v1/kb/search` (PageIndex tree reasoning + dense rerank).
4. Agent chat streams via `GET /api/v1/agent/chat` (SSE; LangGraph nodes invoke tools in `agent/tools.py`).

**Lazy-loaded model backends** (no prewarm except OpenKB): `moldet` (YOLO26n), `molscribe` (Swin + TR), OCR cloud chain (MinerU → PaddleOCR → GLMOCR → RapidOCR). First request per backend pays 5–30 s load cost — see `TODO/INDEX.md` C-4.

**Storage locations:**
- Per-project canonical: `{root}/storage/{doc_id}/` (source.pdf, reorganized.md, crops/, pages/) — managed by `core/artifact.py:ArtifactResolver`
- Per-project legacy: `{root}/.mbforge/crops/{doc_id}/` (read-only fallback until `scripts/migrate_artifact_paths.py` runs)
- Per-project DB: `{root}/.mbforge/knowledge_base.db` + OpenKB + PageIndex collection under `openkb/`
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
| Error & logging architecture (severity ladder, diagnostics endpoint, JSON schema) | [docs/architecture/error-logging.md](./docs/architecture/error-logging.md) |

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

### Commit Granularity — 一主题 = 一 commit

**不要按文件拆 commit，按主题拆。** 一个 feature / refactor / bug fix
即使横跨 15 个文件，仍然作为**一个原子 commit** 提交；其内部的子
步骤写在 commit body 中（用 Markdown `- [ ]` 清单），而不是拆成多个
小 commit。

提交 body 用 Markdown 详细描述：

- **Why** — 背景、动机、影响范围
- **What** — 文件分组 + 子任务清单（`- [ ]`）
- **Breaking changes** — API/字段重命名、迁移步骤
- **Verify** — 验证方法（命令、测试名）
- **Rollback** — 回滚方法（revert commit hash、注意事项）

**应该拆 commit**：不相关的 chore、独立 feature、版本 bump、独立 bug 修复。
**应该合并 commit**：单个 refactor 涉及的所有文件、单个 feature 的
前后端 + 文档、一次清理活动的所有步骤。

反例：
```
chore: rename project_root → library_root in app.py
chore: rename project_root → library_root in pipeline.py
chore: rename project_root → library_root in knowledge_base.py
```

正例：
```
refactor(core): migrate project management to unified library

- [ ] backend: app.py swap project router → library router
- [ ] backend: rename project_root → library_root across callers
- [ ] backend: replace index.json scan with LibraryStore queries
- [ ] frontend: GroupsPanel + RecentProjectsSection update
- [ ] delete dead project router / core.project / models.project
```
