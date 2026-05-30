# AGENTS.md — MBForge

uv workspace root (`pyproject.toml`). Main package `mbforge` under `src/`.

## Commands

```bash
uv sync --dev              # install all deps (includes openSAR + UniParser-Tools workspace members)
uv run pytest tests/ -v    # test import mode: importlib, src path added via conftest.py
uv run pytest tests/unit/test_project.py -v   # single file
uv run ruff check src/     # lint
uv run ruff format src/    # format after check
uv run mypy src/           # type check
cd frontend && npm run dev # Vite on :5173, proxies /api to :18792
uv run uvicorn mbforge.model_server.main:app --host 127.0.0.1 --port 18792
cd frontend && npm run build  # runs tsc && vite build (no separate typecheck command)
cd src-tauri && cargo tauri build  # desktop bundle
```

## Developer setup

**Both** Vite dev server (`:5173`) and model server (`:18792`) must run for development. Two terminals needed. The `mbforge dev` CLI spawns both automatically.

Always `cp .env.template .env` and configure API keys before running.

Fixture path: `tests/conftest.py` inserts `src/` into `sys.path`. Test discovery uses `--import-mode=importlib`.

## Package quirks

- PyTorch pinned to CUDA 12.8 index via `[tool.uv.sources]` — `uv add torch` auto-resolves to `pytorch-cu128` index
- pandas and numpy overridden to `<2.0` / `<3.0` — `[tool.uv] override-dependencies`
- UV index set to Tsinghua mirror (not PyPI) by default — `[tool.uv] index-url`
- `openSAR` and `UniParser-Tools` are uv workspace members in `setup/`, NOT installed as separate packages
- Python entrypoints: `mbforge = mbforge.cli:main` and `csar = mbforge.csar_main:main` in `[project.scripts]`

## Architecture at a glance

| Layer | Dir | Entrypoint |
|-------|-----|------------|
| CLI | `src/mbforge/cli.py` | `main()` — subcommands: `dev`, `gui`, `init`, `index`, `download` |
| Model server | `src/mbforge/model_server/main.py` | FastAPI app, 14 routers under `/api/v1/*` |
| Agent | `src/mbforge/agent/agent.py` | `ProjectAgent` ReAct loop |
| Core data | `src/mbforge/core/` | Project, KnowledgeBase (ChromaDB), MoleculeDatabase (SQLite+RDKit) |
| Frontend | `frontend/src/App.tsx` | React Router with 7 routes |
| Tauri | `src-tauri/src/main.rs` | Desktop shell, spawns Python sidecar |

`CLAUDE.md` in root has full module tables, data flow diagrams, and code patterns for adding endpoints/tools/models.

## External services (configured in .env)

- **LLM**: OpenAI-compatible API (SiliconFlow, vLLM, Ollama, etc.) — set `MBFORGE_LLM_*` env vars
- **Embedding**: default local `sentence-transformers` (BAAI/bge-small-zh-v1.5), or API via `MBFORGE_EMBED_*`
- **UniParser**: remote API `UNIPARSER_HOST` + `UNIPARSER_API_KEY` (currently unused — core uses local PyMuPDF)
- **MinerU**: optional, `MINERU_HOST` + `MINERU_API_KEY`

## Caveats

- Frontend `api/client.ts` and `types/index.ts` are **never to be modified** per DEV_GUIDE.md
- `frontend/vite.config.ts` and `frontend/package.json` are also protected
- Integration test dir `tests/integration/` is empty — don't assume integration tests exist
- The `csar` CLI (`uv run csar`) is merged into `src/mbforge/` from openSAR but not yet wired into mbforge core
- On error: describe the symptom, understand the cause, propose a fix — don't blindly try variations
