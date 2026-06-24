# Repository Guidelines

> Practical guide for AI assistants working on MBForge. Covers architecture, conventions, and the day-to-day commands needed to add a feature, fix a bug, or run tests.

## Project Overview

**MBForge** is a desktop knowledge-work platform for molecular science and drug discovery. It ingests scientific PDFs, extracts molecules and activities, indexes them into a searchable knowledge base, and exposes an AI agent for cross-document reasoning.

Pipeline: `PDF → parse → molecule extraction → vector KB + molecule DB → agent chat`.

Stack:

- **Frontend**: React 19 + Vite 8 + TypeScript 6, runs in Tauri WebView and (for UI work) in the browser.
- **Desktop shell**: Tauri v2 (Rust 2021). Owns IPC, SQLite persistence, native PDF parsing, and the agent ReAct loop.
- **Python sidecar**: FastAPI on `127.0.0.1:18792`. Hosts 4 backends: `qwen3` (embed + rerank), `molscribe`, `moldet`.

## Architecture & Data Flow

Five-layer split, top-down:

| Layer | Path | Responsibility |
|---|---|---|
| UI | `frontend/src/` | React components, routing, AppContext global state |
| IPC | `src-tauri/crates/mbforge-app/src/commands/` | `#[tauri::command]` handlers; bridge frontend ↔ core |
| Core | `src-tauri/crates/mbforge-{domain,chem,infra,pipeline}/` | Domain logic, persistence, embeddings, chem, pipeline |
| Models | `src/mbforge/server.py` + `src/mbforge/backends/` | FastAPI + 5 local model backends (incl. Zvec) |

**Data flow** (PDF in → query out):

1. Frontend uploads PDF via `file_ops::upload_files` → stored under `{project_root}/`.
2. `pipeline::process_document` classifies the doc (paper / patent / report), routes to a parser client (lopdf / LlamaParse / MinerU / UniParser / PaddleOCR), runs MolDet + MolScribe on figures.
3. `pipeline::index_project` writes results: vectors → `.mbforge/search.zvec` (Zvec dense + FTS + hybrid), molecules → `molecules.db` (SMILES + 2048-bit Morgan fingerprint), semantic cache → `semantic_cache.json`.
4. Frontend queries via `kb_search` / `kb_search_stream` (RRF fusion of Zvec FTS + cosine); molecule ops go through `molecule` / `mol_store` / `molecule_admin` / `chem_ops`.
5. Agent chat (`agent_chat_stream`) runs ReAct over `agent` tool set (KB search, molecule search, document fetch, etc.) and streams back to UI.

**Cross-boundary data types**: `ParsedDocument`, `Section`, `Molecule`, `AgentTrajectory` — all serialized as JSON across Tauri IPC.

## Key Directories

```
MBForge/
├── frontend/                       React + Vite app
│   └── src/
│       ├── api/tauri/              IPC wrappers (one file per backend module)
│       ├── components/             Page-level components + ui/ atoms
│       ├── context/AppContext.tsx  Global state (projectRoot, tabs, active file)
│       ├── hooks/                  useTheme, useAnimations, useToast, etc.
│       ├── styles/                 CSS variables + theme tokens
│       └── test/setup.ts           @testing-library/jest-dom
├── src-tauri/
│   ├── Cargo.toml                  Rust workspace (5 members)
│   ├── crates/
│   │   ├── mbforge-app/            Tauri entry, commands, sidecar control
│   │   ├── mbforge-domain/         Document, KB, vector, project, resource manager
│   │   ├── mbforge-infra/          Config, AppError, HTTP clients, helpers
│   │   ├── mbforge-chem/           Molecules, fingerprints, Markush
│   │   └── mbforge-pipeline/       PDF parsing pipeline + ingest worker
│   ├── tests/pipeline_v2.rs        Workspace integration test
│   └── .cargo/config.toml          rustflags = ["-Awarnings"] (suppresses warnings)
├── src/mbforge/                    Python sidecar
│   ├── server.py                   FastAPI app + lifespan prewarm
│   ├── __main__.py                 `python -m mbforge` → uvicorn
│   ├── backends/                   qwen3.py, molscribe.py, moldet.py, zvec_backend.py
│   └── parsers/molecule/           MolScribe inference, coords, coref
├── tests/                          Python tests (unit/, parser_io/, integration/)
├── docs/                           Specs, plans, references
├── setup/                          8-module installer (index.sh / index.bat)
├── TODO/INDEX.md                   Master task board
├── pyproject.toml                  uv + ruff + pytest
├── uv.lock                         Python lock
└── .env.template                   Environment variable template
```

## Development Commands

Run from `MBForge/`.

### Install

```bash
uv sync --dev                  # Python deps (uv, not pip)
npm --prefix frontend install   # Frontend deps
```

### Run (3 terminals)

```bash
# 1. Python sidecar
uv run uvicorn mbforge.server:app --host 127.0.0.1 --port 18792

# 2. Frontend dev server (Vite proxies /api → 18792)
cd frontend && npm run dev

# 3. Tauri desktop shell (Rust side changes only)
cd src-tauri && cargo tauri dev
```

For browser-only UI work, add `?devmock=1` to load the embedded mock that maps ~25 Tauri commands to in-memory data.

### Compile / typecheck

```bash
cd src-tauri && cargo check                 # Rust (warnings suppressed via .cargo/config.toml)
cd frontend && npx tsc --noEmit            # TS strict mode
uv run ruff check src/                      # Python lint
uv run ruff format src/ --check             # Python format
```

To surface Rust warnings during dev, comment the `rustflags` line in `src-tauri/.cargo/config.toml`.

### Production build

```bash
cd frontend && npm run build                # outputs frontend/dist
cd src-tauri && cargo tauri build           # bundles desktop app
```

`tauri.conf.json` runs `npm --prefix ../../../frontend run build` automatically before bundling.

## Code Conventions & Common Patterns

### Rust

- **State**: prefer `Arc<tokio::sync::Mutex<T>>` for async state (P1 migration in progress); legacy code still uses `std::sync::Mutex` (e.g. `sidecar.rs`) — match the local pattern. Tauri state via `.manage(*State::new())` in `main.rs`; access via `app.state::<*State>()`.
- **Errors**: core returns `AppResult<T>` (`Result<T, AppError>`) using `thiserror`. **Tauri commands** must convert: `AppResult<T> -> Result<T, String>` via `.map_err(|e| e.to_string())`. Never `unwrap()` in non-test code. `log::info!` / `log::warn!` / `log::error!` only — no `println!`.
- **Async**: `tauri::async_runtime::spawn` for background tasks. `mpsc::channel(32)` for download progress. `Arc<AtomicBool>` for cancel flags (see `resource_manager.rs`).
- **HTTP**: 4 `LazyLock<reqwest::Client>` singletons at timeouts 15s/30s/120s/300s in `crates/mbforge-infra/src/http.rs`. Use `client_15s()` etc. — never construct a new client.
- **Path safety**: all path joins must go through `core/helpers.rs::safe_join` / `assert_within_root`. Direct `Path::join` + filesystem access is a code-review red flag.
- **No `unsafe`**. No new `unsafe` blocks permitted.
- **Clippy**: `#![allow(...)]` for legacy patterns in `main.rs`; new code should pass clippy.
- **Naming**: `snake_case` for functions/vars, `PascalCase` for types, `SCREAMING_SNAKE_CASE` for consts. Booleans prefixed `is_`/`has_`/`can_`. Tauri commands follow `{module}_{action}` (e.g. `agent_init`, `mol_store_search`).

### Python

- **Logger**: every module starts with `logger = get_logger(__name__)`. Never `print()`.
- **Exceptions**: inherit from `MBForgeError` (`src/mbforge/utils/helpers.py`) with `status_code` + `error_code` class attrs. FastAPI handler maps to `{success: false, error, error_code}`. No bare `except:`.
- **Async I/O**: wrap blocking calls with `await loop.run_in_executor(None, lambda: ...)` — the `server.py` file does this for 11+ model calls.
- **Type hints**: use `from __future__ import annotations` to avoid runtime forward refs. Public functions must be fully annotated.
- **Lint/format**: ruff (select E/F/I/N/W/UP/B/C4/SIM), `ruff format` at line-width 88.

### TypeScript / React

- **Components**: `export default function ComponentName()` for page-level; `function SubComponent()` for local UI. Hooks prefixed `use`.
- **State**: local → `useState`; cross-component → props; global → `useAppContext()`. Persistent settings use `localStorage` with `mbforge_` prefix.
- **IPC**: every Tauri call goes through `api/tauri/*.ts`. Pattern: `await invoke<T>('command_name', { root, docId })` wrapped in `invokeWithError` (see `_utils.ts`). Use `isTauriAvailable()` for browser fallback; `// DEV ONLY` comments on HTTP fallbacks.
- **Animations**: import variants from `hooks/useAnimations.ts` (`fadeUp`, `scaleIn`, `staggerContainer`, …). Do not redefine `initial/animate/exit/transition` inline.
- **Imports**: `@/` alias for `frontend/src/`; `import type` for type-only imports; three groups (std → third-party → project) separated by blank lines.
- **Style**: prefer CSS variables (`var(--accent)`, `var(--bg-surface)`); inline `style` ≤ 3 props, otherwise extract. Verify dark mode for new styles.
- **TS strict**: `strict`, `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch` all on.

### Common patterns

- **Adding a Tauri command**: define `#[tauri::command]` in the appropriate `commands/{module}.rs` → append one line to `commands::handler()` in `commands/mod.rs` → add the command name to `permissions/allow-app-commands.toml`.
- **Adding a Python endpoint**: route in `server.py` with prefix `/api/v1/{resource}`; if a new backend, create `backends/{name}.py` and register in `_BACKENDS`.
- **Adding a Rust agent tool** (rig-core pattern): `struct <Name>Tool` + `Args` in `core/agent/executor_rig.rs`; implement `Tool` calling `core/agent/{fs,kb,document,molecule}.rs::native_*`; register in `rig_adapter.rs::assemble_rig_tool_vec()`.

## Important Files

| File | Role |
|---|---|
| `src-tauri/crates/mbforge-app/src/main.rs` | Tauri entry: dotenv walk, sidecar spawn, ingest worker start, signal handlers |
| `src-tauri/crates/mbforge-app/src/commands/mod.rs` | Aggregates all IPC handlers via `tauri::generate_handler!` |
| `src-tauri/crates/mbforge-app/permissions/allow-app-commands.toml` | Per-command allowlist (must mirror `handler()`) |
| `src-tauri/crates/mbforge-app/tauri.conf.json` | `devUrl: 5173`, `frontendDist: frontend/dist`, `beforeBuildCommand: npm build` |
| `src-tauri/crates/mbforge-app/capabilities/default.json` | Tauri capability source of truth |
| `src-tauri/crates/mbforge-infra/src/config/settings.rs` | `AppConfig` (global) — model_server, llm, embed, rerank, ocr, vlm, theme |
| `src-tauri/crates/mbforge-infra/src/config/llm_config.rs` | Env precedence: `MBFORGE_LLM_*` > `config.json` |
| `src-tauri/crates/mbforge-infra/src/http.rs` | 4× `LazyLock<reqwest::Client>` at 15s/30s/120s/300s |
| `src-tauri/crates/mbforge-infra/src/helpers.rs` | `safe_join` / `assert_within_root` — path safety |
| `src-tauri/crates/mbforge-infra/src/error.rs` | `AppError` + `AppResult<T>` + `From` impls |
| `src-tauri/crates/mbforge-pipeline/src/ingest_worker/mod.rs` | Worker loop with `AtomicBool` + `Interval` heartbeat |
| `src/mbforge/server.py` | FastAPI app, 11+ endpoints, lifespan prewarms 4 backends |
| `src/mbforge/__main__.py` | `python -m mbforge` → uvicorn on port 18792 |
| `src/mbforge/utils/helpers.py` | `MBForgeError` + 7 subclasses |
| `frontend/src/main.tsx` | React 19 root, BrowserRouter, App |
| `frontend/src/context/AppContext.tsx` | Global state: `projectRoot`, `openTabs`, `activeTabId` |
| `frontend/src/api/tauri/_utils.ts` | `invokeWithError` wrapper + `isTauriAvailable()` |
| `frontend/src/hooks/useAnimations.ts` | framer-motion variants hub (fadeUp, stagger, modalEntrance, …) |
| `frontend/index.html` | Mounts `#root`; embeds devmock when `?devmock=1` |

**Configuration precedence**: GUI settings > env vars > `config.json` defaults.

**Storage locations** (per project): `{root}/index/molecules.db`, `{root}/.mbforge/knowledge_base.db` (SQLite business tables), `{root}/.mbforge/search.zvec/` (Zvec collection for vectors + FTS), `{root}/.mbforge/cache/semantic_cache.json`. Global config: `~/.config/MBForge/config.json` (Linux) / `%APPDATA%\MBForge\config\config.json` (Windows).

## Runtime & Tooling Preferences

| Tool | Choice | Notes |
|---|---|---|
| Python package manager | **uv** (NOT pip) | `uv sync --dev`, `uv run` for execution |
| Python venv | `.venv` at project root | `uv venv` |
| Rust toolchain | stable, **edition 2021** | No `rust-toolchain.toml` pinned |
| Frontend | **npm** (NOT pnpm/bun/yarn) | `package-lock.json` is the lock |
| Node version | >=18 (Vite 8 baseline) | No `.nvmrc` |
| Lint/format (Rust) | `cargo check` (warnings hidden by default) | rustfmt at `max_width=100` |
| Lint/format (Python) | ruff (E/F/I/N/W/UP/B/C4/SIM) | `ruff format` at width 88 |
| Lint/format (TS) | eslint + typescript-eslint `strictTypeChecked` + custom `local/no-ampersand-style` | Run via `npm run lint` |
| Tauri CLI | `cargo tauri` (NOT `npx tauri`) | `cargo tauri dev` / `cargo tauri build` |
| GPU | CUDA 12.8 (PyTorch wheel index `pytorch-cu128`) | Required only for `moldet`/`molscribe`; LLM/embed run on CPU |
| Tauri v2 permissions | `permissions/allow-app-commands.toml` + `capabilities/default.json` | Both must be updated together |

**.env template** (`.env.template`): `MBFORGE_{LLM,EMBED,RERANK,VLM}_*` for providers; `HF_HOME`, `MODELSCOPE_CACHE`, `TORCH_HOME` for caches; `UNIPARSER_*`, `MINERU_*`, `DEEPXIV_API_KEY` for remote parsers.

## Testing & QA

### Frameworks

- **Rust**: `#[cfg(test)] mod tests` (in-module) + `src-tauri/tests/pipeline_v2.rs` (workspace integration). ~55 in-module test mods across 5 crates.
- **Python**: pytest. 8 files: `tests/unit/` (6 files), `tests/parser_io/`, `tests/integration/`. `pyproject.toml` sets `testpaths = ["tests"]`.
- **Frontend**: vitest 4 + jsdom + `@testing-library/jest-dom` (via `frontend/src/test/setup.ts`). 19 test files in `src/**/*.test.{ts,tsx}`. Coverage via `@vitest/coverage-v8` (configured but only used on Button/Card/Tabs).

### Running tests

```bash
# Rust — module-scoped during dev, full suite for CI
cd src-tauri && cargo test --lib vector::
cd src-tauri && cargo test --lib document::
cd src-tauri && cargo test --lib molecule::
cd src-tauri && cargo test --lib parsers::
cd src-tauri && cargo test --lib agent::
cd src-tauri && cargo test --lib                 # full suite

# Python
uv run pytest tests/ -v

# Frontend
cd frontend && npm run test                     # vitest run
cd frontend && npm run test:ui                  # vitest with UI
cd frontend && npm run test -- --coverage       # v8 coverage
```

### Conventions

- **Test names**: `test_{feature}_{scenario}` (e.g. `test_detect_type_pdf`).
- **Test intent**: assertions express *why* the behavior matters, not just *what* it does. Tests that pass when business logic is wrong are design failures.
- **No mocks of real systems**: HTTP clients use `mockito` or custom stubs. DB tests use temp dirs or in-memory SQLite.
- **No CI configured**: no `.github/workflows/`. Pre-release checklist is manual: `cargo check` + `tsc --noEmit` + `ruff check` + `pytest` + per-module `cargo test`.

### Coverage

- Frontend: `@vitest/coverage-v8` reports to `frontend/coverage/`.
- Rust: not configured. (No `cargo-llvm-cov` / `tarpaulin` integration.)
- Python: `pytest-cov` is declared in `pyproject.toml` but not invoked in any target. Coverage goal ≥70% on core logic per AGENTS spec.

---

**Don't see what you need?** Check `docs/` (8 top-level + 6 specs + 22 superpowers plans), `TODO/INDEX.md` (master task board, P0–P3 priorities), or `archived/` for deprecated subsystems (e.g. legacy agent code lives under `archived/agent/`).
