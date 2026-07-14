# Repository Guidelines

## Project Structure & Module Organization

The FastAPI backend lives in `src/mbforge/`: HTTP handlers are in `routers/`,
business and storage logic in `core/`, the seven-stage workflow in `pipeline/`,
model wrappers in `backends/`, and Pydantic schemas in `models/`. The React 19
and TypeScript 6 frontend is under `frontend/src/`; keep REST clients in
`api/http/`, React Query hooks in `api/query/`, and UI code in `components/`.
Tests are split between `tests/unit/` and `tests/integration/`; frontend tests
are colocated as `*.test.ts` or `*.test.tsx`. Documentation belongs in `docs/`
(see [docs/README.md](docs/README.md)); development assets in `assets/`.
Business config is `~/MBForge/settings.json` via `mbforge.utils.config` — there
is no runtime `configs/` directory.

## Build, Test, and Development Commands

Use Python 3.12, `uv`, and Node 20.19 or newer.

```bash
uv sync --dev                         # update .venv
npm --prefix frontend install         # install frontend dependencies
uv run uvicorn mbforge.app:app --host 127.0.0.1 --port 18792
npm --prefix frontend run dev         # Vite on :5173; proxies /api
uv run ruff check src tests            # Python lint
uv run ruff format src tests --check   # Python formatting check
npm --prefix frontend run lint         # ESLint
npm --prefix frontend run build        # type-check and production build
```

Do not leave verification servers running on the default ports.

## Coding Style & Naming Conventions

Python uses four spaces, complete public type hints, `snake_case` functions,
`PascalCase` classes, and Ruff's 88-column format. Use `get_logger(__name__)`,
never `print()` or bare `except`. API boundaries use Pydantic models. Offload
blocking work from async handlers with `asyncio.to_thread()` or an executor.

TypeScript is strict. Use `PascalCase` components, `useCamelCase` hooks, and
`import type` for type-only imports. Cross-directory imports use `@/`. Route
HTTP through `api/http`, prefer React Query for server state, and reuse shared
CSS variables and animation hooks.

## Testing Guidelines

Run `uv run pytest tests/ -q` and `npm --prefix frontend run test`. Add focused
regression tests named `test_<behavior>_<scenario>`; use `tmp_path` and real
SQLite where practical. Check coverage with
`uv run pytest tests/ --cov=src/mbforge --cov-report=term-missing`.

## Commit & Pull Request Guidelines

Use Conventional Commits, for example `fix(coref): reject traversal doc ids`.
One logical change equals one commit and one PR. PRs must link the Issue/TODO,
explain scope, record verification results, and state risks, migrations, and
rollback steps. Include screenshots for UI changes, update relevant docs and
`CHANGELOG.md` for user-visible behavior, and avoid unrelated churn.

## Security & Configuration

Never commit secrets, PDFs, model weights, logs, or real library data. Access
global settings only through `mbforge.utils.config`; use `library_root` (Python)
and `libraryRoot` (TypeScript), never deprecated project-root aliases. Resolve
library paths through `LibraryLayout` and document artifacts through
`ArtifactResolver`; do not construct storage paths directly.
