# docs/ — Documentation index

> **Last sync**: 2026-07-14  
> Living docs describe current code. Dated analysis/reviews/research are
> **historical** unless marked otherwise. If a living doc conflicts with code,
> **the code wins** — fix the doc in the same change.

## Living (keep in sync with code)

| Path | Role |
|---|---|
| [../README.md](../README.md) | Human product entry, quick start |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Dev / test / PR workflow |
| [../AGENTS.md](../AGENTS.md) | AI contributor short guidelines |
| [../CLAUDE.md](../CLAUDE.md) | AI architecture quick-ref + commands |
| [../TODO/INDEX.md](../TODO/INDEX.md) | Prioritized task board (P0–P3) |
| [PROJECT_MANAGEMENT.md](PROJECT_MANAGEMENT.md) | Work-item governance |
| [VERSION_CONTROL.md](VERSION_CONTROL.md) | Branches, commits, SemVer, releases |
| [REFERENCES.md](REFERENCES.md) | Third-party attribution |
| [specs/](specs/) | Architecture conventions, code style, molecule representation |
| [architecture/pipeline-stages.md](architecture/pipeline-stages.md) | 7-stage pipeline reference |
| [architecture/error-logging.md](architecture/error-logging.md) | Error / diagnostics model |
| [adr/](adr/) | Architecture decision records (immutable history + status notes) |

Specs index: [specs/README.md](specs/README.md).

## Historical / snapshot (do not treat as current API)

These files record a point-in-time analysis or review. Numbers (router count,
stage count, coverage %, path layout) may be **wrong today**. Use for context
only; verify against code before acting.

| Area | Contents |
|---|---|
| [analysis/](analysis/) | Defect / frontend optimization write-ups (2026-07) |
| [reviews/](reviews/) | Code / pipeline review reports (incl. pre-Python Rust pipeline) |
| [architecture/DISCUSSION-*.md](architecture/) | Product discussion notes |
| [architecture/PHASE0-SCOPE.md](architecture/PHASE0-SCOPE.md) | Phase 0 scope snapshot |
| [pageindex-research.md](pageindex-research.md) | Pre-migration PageIndex research (Rust paths historical) |
| [superpowers/](superpowers/) | Past implementation plans |
| [../TODO/EVIDENCE-PHASE1-COMPLETE.md](../TODO/EVIDENCE-PHASE1-COMPLETE.md) | Completion record |
| [../TODO/IMMEDIATE-ACTIONS.md](../TODO/IMMEDIATE-ACTIONS.md) | Dated action list |
| [../TODO/PHASE0-ROADMAP.md](../TODO/PHASE0-ROADMAP.md) | Phase 0 roadmap (living-ish; still check INDEX) |

## Canonical facts (2026-07-14)

- **Pipeline**: 7 logical stages — Extract → Density → Markdown → Reorganize →
  Activity → Index → Persist (`src/mbforge/pipeline/runner.py`).
- **UI**: `frontend/` only.
- **Entry**: `uv run uvicorn mbforge.app:app --host 127.0.0.1 --port 18792` or
  `python -m mbforge`.
- **Library root field**: `library_root` / `libraryRoot` (no new `project_*`).
- **DB**: `{library_root}/.mbforge/library.db`.
- **Artifacts**: `{library_root}/storage/{doc_id}/` via `ArtifactResolver`.
- **Python**: 3.12 only; package manager **uv**; frontend **npm**.

## Doc ownership (who edits what)

| Audience | Primary files |
|---|---|
| Humans (install / product) | README, CONTRIBUTING, CHANGELOG |
| AI coding sessions | CLAUDE.md (big picture), AGENTS.md (rules) |
| Architecture / contracts | docs/specs, docs/architecture, docs/adr |
| Priority work | TODO/INDEX.md |

Governance process detail: [../.claude/documentation-governance.md](../.claude/documentation-governance.md)
(refreshed for Python-only stack).
