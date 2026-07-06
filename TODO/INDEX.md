# MBForge Master Task Board

> Single source of truth for prioritized work. Replaces the deprecated root
> `TODO.md` (now removed during the 2026-06-29 Rust→Python migration).
>
> Generated from a comment / drift audit of the post-migration codebase.
> If you find a new issue, append it here — not in a side file.

## Legend

| Priority | Meaning |
|---|---|
| P0 | Critical: blocks startup / production runs / data loss |
| P1 | High: data loss, panic paths, doc drift that misleads new contributors |
| P2 | Medium: code quality, doc/comment drift, lint violations |
| P3 | Low: stylistic, anchors, type-hint polish |

## Snapshot

- **Last drift-sync**: 2026-07-05
- **Snapshot at**: 2026-06-29 (post-migration audit)
- **Codebase**: Python-only backend, OpenKB + PageIndex (KB), 18 FastAPI routers
- **Head at sync**: `371d6dc docs: add Phase 1 implementation plan and SAR pipeline design spec`
- **Coverage**: Python ~5% (only `tests/unit/parsers/test_coref_alt.py` populated)
- **Tech debt theme**: tests + frontend→backend contract drift; stale src-tauri/ refs and Zvec→OpenKB migration leftovers

---

## P0 — Critical (run-blockers)

| ID | Area | Finding | File | Status |
|---|---|---|---|---|
| C-1 | Repo | `ts_errors.txt` (36.6 KB) sits at repo root, not in `.gitignore`. Will be picked up by `git add .` and committed. | `ts_errors.txt` | **OPEN** |
| C-2 | Config | `.gitignore` typo: `.mbforge/` was changed to `.mbccforge/`. Project runtime data would be tracked by git. | `.gitignore` | **OPEN** |
| C-3 | Config | `frontend/tsconfig.json` has the key `"noCheck": true` listed twice (duplicate). TS compiler tolerates it but lint flags it. | `frontend/tsconfig.json` | **OPEN** |
| C-4 | Backend | `app.py` lifespan does not prewarm any backend — `server.py:_prewarm()` is a no-op. First request to embed / rerank / moldet / molscribe pays 5–30s model load. No UX handles this gracefully. (Previously referenced Zvec prewarm; Zvec removed in commit `4fbde55`.) | `src/mbforge/app.py`, `src/mbforge/server.py`, `src/mbforge/backends/{qwen3,moldet,molscribe}.py` | **OPEN** |
| C-5 | Frontend | `frontend/src/api/tauri/_utils.ts` was rewritten to use HTTP, but the directory is still named `api/tauri/`. Confuses contributors searching for IPC code. | `frontend/src/api/tauri/` | **OPEN** |

## P1 — High (data loss, runtime crashes, doc drift)

| ID | Area | Finding | File | Status |
|---|---|---|---|---|
| R-1 | Tests | No Python test covers any of the 53 routes in `app.py`. A single regression in router wiring goes undetected. | `src/mbforge/app.py`, `src/mbforge/routers/*.py` | **OPEN** |
| R-2 | Tests | `pipeline/{classify,extract_text,segment,chunk,index,runner}.py` (~900 lines new) has zero unit tests. Stage failures are silent. | `src/mbforge/pipeline/` | **OPEN** |
| R-3 | Tests | `core/{database,knowledge_base,semantic_cache,project}.py` (~600 lines new) has zero unit tests. RRF fusion logic untested. | `src/mbforge/core/` | **OPEN** |
| R-4 | Tests | `agent/{graph,tools,sessions,llm_factory}.py` (~375 lines new) has zero tests. LangGraph tool wiring could regress. | `src/mbforge/agent/` | **OPEN** |
| R-5 | Frontend | SSE client (`api/sse.ts`) has no reconnect/backoff logic documented. A flaky network mid-stream produces truncated agent answers. | `frontend/src/api/sse.ts` | **OPEN** |
| R-6 | Frontend | `httpFetch` error mapping (`api/http/_utils.ts`) doesn't cover all FastAPI error shapes (e.g., `MBForgeError` 422 vs HTTP 422). Need spec test. | `frontend/src/api/http/_utils.ts` | **OPEN** |
| R-7 | Backend | `backends/qwen3.py:1` header docstring still says "embed + rerank" but module now hosts `EmbeddingProvider`, `OpenAICompatibleProvider`, multi-LLM dispatch. Update header. | `src/mbforge/backends/qwen3.py` | **OPEN** |
| R-8 | Backend | `core/resource_manager.py` adds 245 lines including `subprocess.run(['nvidia-smi'], timeout=5)` blocking calls on hot path. Need async wrapper + cached result. | `src/mbforge/core/resource_manager.py` | **OPEN** |
| R-9 | Docs | `CLAUDE.md` (newly created) lists `archived/agent/` paths in error examples. `archived/` no longer exists. | `CLAUDE.md` | **RESOLVED 2026-07-05** |

## P2 — Medium (drift, type hints, docstring quality)

| ID | Area | Finding | File | Status |
|---|---|---|---|---|
| D-1 | Tests | `tests/unit/test_pipeline.py`, `tests/unit/test_embed_rerank.py`, `tests/unit/test_zvec_service.py`, `tests/unit/test_agent.py`, `tests/unit/parsers/test_molecule_parsers.py`, `tests/integration/test_real_pdfs.py` referenced in prior `TODO/INDEX.md` no longer exist. Either re-create or update references. | `TODO/INDEX.md:60` (history) | **OPEN** |
| D-2 | Python | `backends/moldet.py` switched to `moldet_v2_yolo26n_960_doc.pt` with conf_threshold 0.5 but no test asserts the new defaults. | `src/mbforge/backends/moldet.py` | **OPEN** |
| D-3 | Python | `parsers/molecule/coref_alt.py` had 139 lines changed; only one new test added. Cross-page join edge cases under-tested. | `src/mbforge/parsers/molecule/coref_alt.py` | **OPEN** |
| D-4 | Python | `backends/zvec_backend.py:_validate_index_payload` raises `ValidationError` but `zvec_backend.py:163` line wrap produces 3-line error message — reformat for grep-friendliness. | `src/mbforge/backends/zvec_backend.py:163` | **OPEN** |
| D-5 | Python | `utils/helpers.py:run_sync` signature uses `"Callable[..., Any]"` quoted form in some places, unquoted in others. Pick one (Python 3.11+ allows unquoted). | `src/mbforge/utils/helpers.py` | **OPEN** |
| D-6 | Frontend | `_utils.ts` header comment says "HTTP communication layer — replaces Tauri IPC for web mode" but file is still in `api/tauri/` directory. Move to `api/http/`. | `frontend/src/api/tauri/_utils.ts` | **OPEN** |
| D-7 | Deps | `pyproject.toml:79` `pandas>=3.0.3` — verify against current resolved version in `uv.lock`. | `pyproject.toml` | **OPEN** |
| D-8 | Deps | `langchain>=0.3.0`, `langgraph>=0.4.0` floors are loose; need `uv lock` snapshot of resolved versions to spot breaking changes. | `pyproject.toml`, `uv.lock` | **OPEN** |
| X-1 | Docs | `AGENTS.md` "Storage locations" references `{root}/.mbforge/knowledge_base.db` but `.gitignore` typo (C-2) says `.mbccforge/`. Reconcile. | `AGENTS.md`, `.gitignore` | **OPEN** |
| X-2 | Docs | `README.md` "Tech Stack" still mentions Tauri v2 / Rust in some lines — verify after rewrite. | `README.md` | **OPEN** |
| X-3 | Docs | `docs/REFERENCES.md` lists PyMuPDF, lopdf, ChromaDB, rusqlite — all removed. Updated 2026-06-29. | `docs/REFERENCES.md` | **RESOLVED** |

## P3 — Low (style, anchors, type hints)

| ID | Area | Finding | File | Status |
|---|---|---|---|---|
| S-1 | Python | `server.py` legacy `_CORE_BACKENDS` prewarm comment lists 5 backends; all are comment-only since the migration. Update to no-op prewarm or remove dead reference. (Zvec itself removed in `4fbde55`; only `molscribe` + `moldet` are still real sidecar backends.) | `src/mbforge/server.py:54` | **OPEN** |
| S-2 | Python | `__main__.py` comment is English; `server.py` docstrings are mixed Chinese/English. Pick one convention. | `src/mbforge/__main__.py`, `src/mbforge/server.py` | **OPEN** |
| S-3 | Frontend | `frontend/src/api/sse.ts` uses `EventSource` API; verify behaviour across browsers (Chromium OK, Safari has quirks). | `frontend/src/api/sse.ts` | **OPEN** |
| S-4 | Repo | `assets/models/` referenced in `AGENTS.md` but directory may not exist or be gitignored. | `assets/models/` | **OPEN** |

---

## How this board stays current

- New audits land here as dated P0–P3 sections; resolved items move to a "RESOLVED <date>" tag with the date.
- The deprecated root `TODO.md` is removed; do not recreate it.
- All `code-review` runs and comment-audit sweeps MUST append to this file, not a side file.
- Each P0 item should have a corresponding `git blame` entry or PR link when resolved.

## Recent Resolutions (2026-06-29 migration)

| ID | Description |
|---|---|
| X-3 | `docs/REFERENCES.md` updated: removed lopdf/PyMuPDF/ChromaDB/rusqlite, added pdfplumber/pypdfium2/Zvec/LangGraph. (Subsequently: Zvec itself removed in `4fbde55` and replaced by OpenKB + PageIndex — second pass applied 2026-07-05.) |
| X-2 | `README.md` rewritten: removed all Tauri v2 / Rust mentions, added FastAPI + LangGraph stack table. (Subsequently: Zvec mentions replaced by OpenKB, 5-stage → 6-stage pipeline, src-tauri/ removed entirely — second pass 2026-07-05.) |
| X-4 | `src-tauri/` directory deleted from working tree (~29 GB) — Rust workspace history preserved via `git log -- src-tauri/`. |
| — | `CLAUDE.md` created at repo root (previously session-only at `~/.claude/CLAUDE.md`). |
| — | `AGENTS.md` rewritten to reflect Python-only backend (subsequently: OpenKB + 18 routers + 6-stage pipeline corrected 2026-07-05). |
| R-9 | `CLAUDE.md` no longer references `archived/agent/` — error examples rewritten during 2026-07-05 refresh. |