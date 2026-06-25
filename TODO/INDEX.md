# MBForge Master Task Board

> Single source of truth for prioritized work. Replaces the deprecated root `TODO.md`
> (now `archived/`) and the empty placeholder that previously sat at this path.
> Generated from the 2026-06-25 codebase comment audit.

## Legend

| Priority | Meaning |
|---|---|
| P0 | Critical: blocks startup / production runs |
| P1 | High: data loss, panic paths, doc drift that misleads new contributors |
| P2 | Medium: code quality, doc/comment drift, lint violations |
| P3 | Low: stylistic, anchors, type-hint polish |

## P0 — Critical (run-blockers)

| ID | Area | Finding | File | Status |
|---|---|---|---|---|
| C-1 | Rust+TS | 6 `agent_*` IPC commands (`agent_init` / `agent_create_session` / `agent_chat_stream` / `agent_switch_project` / `agent_clear` / `agent_destroy_session`) called by frontend but **not registered** in `commands/mod.rs`. Remove the broken frontend calls + delete the orphan doc-comment mention in `mol_engine.rs:33`, OR implement them in `commands/agent.rs` against `pipeline/structure/post_process.rs::dispatch_chat`. | `frontend/src/api/tauri/agent.ts:54,84,128,143,150,157`; `src-tauri/crates/mbforge-app/src/commands/mod.rs`; `src-tauri/crates/mbforge-app/src/commands/mol_engine.rs:33` | **OPEN** |
| C-2 | Python | (RESOLVED 2026-06-25) `backends/__init__.py` was missing `moldet`/`molscribe` re-exports — `python -m mbforge` would fail with `ImportError`. Added `from . import moldet  # noqa: F401` and `from . import molscribe  # noqa: F401`. | `src/mbforge/backends/__init__.py:13-14` | DONE |
| C-3 | Docs | `README.md:155,158` references `./setup/index.sh` and `setup\index.bat`; `setup/` directory does not exist. Either re-add the installer or remove the section. | `README.md` | OPEN |
| C-4 | Docs | `AGENTS.md:35` tree lists `setup/  8-module installer` — same path is gone. | `AGENTS.md` | OPEN |
| C-5 | Docs | `AGENTS.md:39` lists `.env.template` at root — file does not exist. | `AGENTS.md` | OPEN |
| C-6 | Rust | (RESOLVED 2026-06-25) `src-tauri/Cargo.toml:10` license was "MIT" but repo `LICENSE` and `pyproject.toml` both declare CC BY-NC-SA 4.0. Changed to `license = "CC-BY-NC-SA-4.0"`. | `src-tauri/Cargo.toml:10` | DONE |
| C-7 | Docs | (RESOLVED 2026-06-25) `TODO/INDEX.md` was 0 bytes. Repopulated with this board. | `TODO/INDEX.md` | DONE |
| C-8 | Docs | `README.md:348,355` link to `docs/esmiles-spec.md` / `docs/molecode-spec.md` / `docs/pipeline-redesign.md` — actual files are at `docs/specs/...`. | `README.md` | OPEN |
| C-9 | Docs | `AGENTS.md:171` says pytest layout includes `tests/parser_io/`, but that directory does not exist. | `AGENTS.md` | OPEN |

## P1 — High (data loss, panics, runtime crashes)

| ID | Area | Finding | File | Status |
|---|---|---|---|---|
| R-1 | Rust | `unreachable!()` in Tauri command match arm — upstream enum gain = IPC panic. Replace with explicit `Err(...)` return. | `src-tauri/crates/mbforge-app/src/commands/settings_extra.rs:80` | OPEN |
| R-2 | Rust | `panic!("invalid label regex ...")` on user-supplied patterns — single bad input crashes the pipeline worker. Convert to `AppError::PdfParse`. | `src-tauri/crates/mbforge-pipeline/src/chem/label_assoc.rs:93` | OPEN |
| R-3 | Rust | TODO at `result_pane.rs:803` — brute-force `delete_coref_predictions` in production path; needs fine-grained delete. | `src-tauri/crates/mbforge-app/src/commands/result_pane.rs:803` | OPEN |
| R-4 | Rust | 5 `eprintln!` calls in production code; AGENTS.md mandates `log::*` only. | `src-tauri/crates/mbforge-pipeline/src/chem/label_assoc.rs:350,378,389,407,409` | OPEN |
| R-5 | Rust | "Placeholder adapter" doc on GLM-OCR / GLM-4.6V-Flash modules wired into Tauri command surface. Implement or `#[cfg(feature=…)]` guard. | `src-tauri/crates/mbforge-pipeline/src/pipeline/services/ocr.rs:203,224` | OPEN |
| R-6 | Rust | "Local (stub)" comments on production Paddle module. Implement or remove. | `src-tauri/crates/mbforge-pipeline/src/ocr/paddle.rs:261,265` | OPEN |
| R-7 | Rust | Crate-level `#![allow(clippy::unwrap_used, clippy::panic)]` in production crate contradicts AGENTS.md "no unwrap in non-test code". | `src-tauri/crates/mbforge-domain/src/lib.rs:7` | OPEN |
| P-1 | Python | 6 `except Exception:` without follow-up comment in chemistry.py. Annotate or narrow. | `src/mbforge/parsers/molecule/molscribe_inference/chemistry.py:42,69,154,417,597,604` | OPEN |
| P-2 | Python | `# TODO-AUDIT: bare except ...` at chemistry.py:418 — author-flagged; resolve or accept and remove. | `src/mbforge/parsers/molecule/molscribe_inference/chemistry.py:418` | OPEN |
| P-3 | Python | Open TODOs in chemistry preprocessing + decoder attn shape. | `src/mbforge/parsers/molecule/molscribe_inference/chemistry.py:556,563`; `transformer/decoder.py:479` | OPEN |
| T-1 | TS | `console.log` calls in production code path; gate with `import.meta.env.DEV` or add `// DEV ONLY` markers. | `frontend/src/api/tauri/project.ts:29-44` | OPEN |
| T-2 | TS | TODO references `AppContext.openDocument()` which is not exported. Implement or remove TODO. | `frontend/src/components/search/SearchResultItem.tsx:61` | OPEN |

## P2 — Medium (drift, type hints, docstring quality)

| ID | Area | Finding | File | Status |
|---|---|---|---|---|
| D-1 | Python | `class TestConfigWithRealPaths` declared twice in same file — pytest only collects the second. Merge or rename. | `tests/integration/test_real_pdfs.py:191,217` | OPEN |
| D-2 | Python | `platformdirs` fallback lambda has wrong signature — produces incorrect Windows paths when `platformdirs` missing. Mirror the real function signature. | `src/mbforge/utils/constants.py:89` | OPEN |
| D-3 | Python | `print("OK: ✓/✗ emitted ...")` in test — AGENTS.md forbids `print()`. Use `logging.info`. | `tests/test_unicode_smoke.py:31` | OPEN |
| D-4 | Python | `subprocess.run(nvidia-smi, timeout=5)` blocks ~5s; doc should warn. | `src/mbforge/core/resource_manager.py:521` | OPEN |
| D-5 | Python | `load_json` / `load_global_config` swallow `JSONDecodeError` / validation errors. Add explanatory comment. | `src/mbforge/utils/helpers.py:117`; `src/mbforge/utils/config.py:112` | OPEN |
| D-6 | Python | `qwen3.py` header says "embed + rerank" — actual module also hosts `EmbeddingProvider`, `OpenAICompatibleProvider`, external-API. Update header. | `src/mbforge/backends/qwen3.py:1` | OPEN |
| D-7 | Rust | Self-contradicting header: "AUTO-GENERATED" + "manually extended" — pick one. | `src-tauri/crates/mbforge-infra/src/config/constants.rs:1-15` | OPEN |
| D-8 | Rust | Orphan "tech debt #2" references in 2 places; ticket never created. | `src-tauri/crates/mbforge-infra/src/config/settings.rs:20,25`; `src-tauri/crates/mbforge-infra/src/db.rs:114` | OPEN |
| D-9 | Python | 6 test modules missing `logger = get_logger(__name__)` (AGENTS.md convention). | `tests/unit/test_pipeline.py`, `tests/unit/test_embed_rerank.py`, `tests/unit/test_zvec_service.py`, `tests/unit/test_agent.py`, `tests/unit/parsers/test_molecule_parsers.py`, `tests/integration/test_real_pdfs.py` | OPEN |
| X-1 | Docs | `README.md` says "Vite 6" — actual is Vite 8. Tech-stack table also wrong on architecture diagram (4 backends vs 5; flat `core/` vs 5-crate workspace). | `README.md:201,230,241` | OPEN |
| X-2 | Docs | `AGENTS.md` says "4 backends" line 9 vs "5 backends (incl. Zvec)" line 11. Reconcile to 5. Also `agent_switch_project` doc-comment path is `archived/agent/` — actual live path is `pipeline/structure/post_process.rs`. | `AGENTS.md:9,11,90,121,140,147,171,202` | OPEN |
| X-3 | Docs | `CLAUDE.md` references `core/agent/`, `core/document/`, `core/vector/`, `core/chem/`, `core/molecule/` — all migrated to `src-tauri/crates/mbforge-{app,domain,chem,infra,pipeline}/`. Update every reference. | `CLAUDE.md:53,73,80,99,118,140` | OPEN |
| X-4 | Docs | `CLAUDE.md:99` lists `backends/qwen3_embed.py` and `backends/qwen3_rerank.py` — both merged into `backends/qwen3.py`. Also `moldet_coref.py` doesn't exist; coref is in `parsers/molecule/coref_alt.py`. | `CLAUDE.md:99` | OPEN |
| X-5 | Deps | `pyproject.toml:79` `pandas>=3.0.3` is unreleased; `>=2.0.0` minimum. | `pyproject.toml:79` | OPEN |
| X-6 | Deps | `pyproject.toml:81` `accelerate>=1.14.0` declared but no `accelerate` import in python sources. Verify and remove. | `pyproject.toml:81` | OPEN |
| X-7 | Deps | `pyproject.toml:23` `pymupdf>=1.23.0` and `transformers>=4.51.0` floors are below lock resolution. Bump. | `pyproject.toml:23` | OPEN |
| X-8 | Deps | `frontend/package.json:5` `engines.node >=18` is below Vite 8 baseline (Node 20.19+ or 22.12+). Bump. | `frontend/package.json:5` | OPEN |

## P3 — Low (style, anchors, type hints)

| ID | Area | Finding | File | Status |
|---|---|---|---|---|
| S-1 | Rust | "Phase 3 重构" anchor on sidecar_client.rs header — phase numbers drift. | `src-tauri/crates/mbforge-infra/src/sidecar_client.rs:2` | OPEN |
| S-2 | Rust | Hardcoded local cache path anchor on smiles.rs header. | `src-tauri/crates/mbforge-chem/src/smiles.rs:2` | OPEN |
| S-3 | Python | `zvec_backend.index_document` iterates `statuses` outside `_WRITE_LOCK` after `delete_by_filter`+`upsert` — docstring should mention read-after-write ordering. | `src/mbforge/backends/zvec_backend.py:194` | OPEN |
| S-4 | Python | `molscribe.predict_batch(images: list)` — inner type missing; tighten. | `src/mbforge/backends/molscribe.py:55` | OPEN |
| S-5 | Python | `qwen3.load(device, **kwargs)` missing `-> None` return type hint. | `src/mbforge/backends/qwen3.py:472` | OPEN |
| S-6 | Rust | `canonicalize_esmiles` actually handles SMILES+ESMILES; rename or split. | `src-tauri/crates/mbforge-domain/src/molecule/molecule_dedup.rs:32` | OPEN |

## How this board stays current

- New audits land here as dated P0–P3 sections; resolved items move to DONE with the date.
- The deprecated root `TODO.md` is archived; do not recreate it.
- All `code-review` runs and comment-audit sweeps MUST append to this file, not a side file.
