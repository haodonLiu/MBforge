# MBForge Repository Restructure — Design Spec

**Date**: 2026-06-24
**Status**: Approved (design phase)
**Scope**: Full code + docs restructuring (top-level zones + per-zone moves + archive)

## 1. Motivation

The MBForge repository has accumulated mixed-purpose artifacts at every level:

- `docs/` mixes specs, plans, research, references, HTML presentations, and DrawIO diagrams in one flat namespace.
- `TODO/` mixes the master task board with dated plans.
- `ref/` mixes external reference PDFs/models with Python/PowerShell helper scripts.
- `setup/MolScribe/` and `ref/MolScribe/` are near-duplicate copies of the same external model.
- Top-level root carries loose files (`PDF_FRONTEND_API.md`, `CODE_REVIEW_REPORT.md`, `constants.yaml`, `reasonix.toml`) with no canonical home.

This makes "where does X go?" a judgment call every time, leading to drift and broken links (already surfaced by `skills/doc-audit/` in commit `26dda20`).

The fix is a three-zone top-level model that clusters by artifact type, plus explicit archive rules for stale plans.

## 2. Goals & Non-Goals

### Goals
1. **Cluster over split**: top-level dirs each hold one artifact type.
2. **No mixing**: code dirs contain no `.md`; doc dirs contain no `.py/.rs/.ts`; plans are date-stamped and archived, not deleted.
3. **Preserve history**: every move uses `git mv` so blame/log stays intact.
4. **Archive, don't delete**: plans untouched ≥1 week move to `archived/`; HTML/bulky artifacts that look "inexplicably useless" move to `archive/`.
5. **Single source of truth**: `.claude/documentation-governance.md` codifies the rules (created in this PR).

### Non-Goals
- No renaming of files inside `frontend/`, `src-tauri/`, `src/` (out of scope; covered by ongoing Rust migration).
- No dedup of `MolScribe-setup/` vs `MolScribe-ref/` — both move to `reference/`, dedup is a follow-up.
- No rewrite of `AGENTS.md` content beyond updating the "Key Directories" section.
- No CI changes.

## 3. Top-Level Architecture (3 Zones)

```
MBForge/
├── code/                (sources that compile/run)
│   ├── frontend/        (React+TS+Vite)
│   ├── src-tauri/       (Rust workspace)
│   ├── src/             (Python sidecar)
│   ├── tests/           (cross-language tests)
│   └── scripts/         (code helpers; merges ref/*.py + ref/*.ps1)
│
├── plans/               (active task board)
│   ├── INDEX.md
│   ├── 2026-06-22-llm-extraction-paper-research.md
│   ├── 2026-06-24-zvec-python-sidecar-plan.md
│   └── archived/        (≥1 week untouched)
│
├── docs/                (timeless reference material)
│   ├── specs/           (canonical — KEEP path)
│   ├── superpowers/     (auto-generated — KEEP path)
│   ├── research/        (investigation notes)
│   ├── references/      (stack, API surface, external notes)
│   ├── plans/           (design-level plans, not dated tasks)
│   ├── audit/           (review reports)
│   ├── diagrams/        (DrawIO)
│   ├── visuals/         (HTML — currently empty)
│   └── archive/         (dead/legacy)
│
├── reference/           (renamed from ref/, external-only)
│   ├── MolScribe-ref/   (← from ref/MolScribe/)
│   ├── MolScribe-setup/ (← from setup/MolScribe/)
│   ├── chematic/, MoleCode/, MolDetect/, PocketXMol/, GESim/
│   ├── paddleocr-vl-local/
│   ├── literature/
│   └── *.PDF, *.mhtml
│
├── configs/             (cross-language source-of-truth configs)
│   └── constants.yaml   (← from root)
│
├── setup/               (installer scripts + modules, no models)
├── archived/agent/      (deprecated subsystems)
├── .claude/             (settings, hooks, skills, governance doc)
└── (root: AGENTS.md, CLAUDE.md, README.md, LICENSE, .env.template,
      .gitignore, .editorconfig, pyproject.toml, uv.lock)
```

### Zone rules
- **`code/`** = runs/compiles. No `.md` plans. `.py/.rs/.ts` allowed.
- **`plans/`** = dated work-in-progress. Archived moves out, never deleted.
- **`docs/`** = timeless reference. Subsplit by *type*: `specs/`, `superpowers/`, `research/`, `references/`, `plans/`, `audit/`, `diagrams/`, `visuals/`, `archive/`.
- **`reference/`** = external materials only. No project code.
- **`configs/`** = cross-language config single-source-of-truth.

## 4. Archive Rules

| ID | Criterion | Destination |
|---|---|---|
| A1 | Plan ≥1 week untouched AND/OR superseded by merged code | `plans/archived/` |
| A2 | Looks "inexplicably useless" (no inbound links + no recent edit + bulky or orphaned) | `docs/archive/` |
| A3 | Old subsystems (e.g. legacy `agent/`) | `archived/{subsystem}/` |
| A4 | Archive is append-only — never delete archived files | (universal) |

## 5. Migration Table

All moves use `git mv` to preserve history.

### 5.1 Top-level loose files

| From | To | Reason |
|---|---|---|
| `PDF_FRONTEND_API.md` | `docs/specs/pdf-frontend-api.md` | API spec |
| `CODE_REVIEW_REPORT.md` | `docs/audit/code-review-report.md` | Audit report |
| `constants.yaml` | `configs/constants.yaml` | Cross-language source of truth |
| `reasonix.toml` | *(delete)* | Gitignored local Claude permission, not project artifact |

### 5.2 `TODO/` → `plans/`

| From | To | Reason |
|---|---|---|
| `TODO/INDEX.md` | `plans/INDEX.md` | Master task board |
| `TODO/2026-06-22-llm-extraction-paper-research.md` | `plans/2026-06-22-llm-extraction-paper-research.md` | Recent (2d) |
| `TODO/2026-06-24-zvec-python-sidecar-plan.md` | `plans/2026-06-24-zvec-python-sidecar-plan.md` | Today |
| `TODO/2026-06-12-processing-queue-ux.md` | `plans/archived/2026-06-12-processing-queue-ux.md` | A1 (12d) |
| `TODO/project-scope-and-queue-plan.md` | `plans/archived/project-scope-and-queue-plan.md` | A1 (12d) |

### 5.3 `docs/` root files

| From | To | Reason |
|---|---|---|
| `docs/REFACTORING-PLAN.md` | `plans/archived/refactoring-plan.md` | A1 (24d, superseded by Phase 6) |
| `docs/moldet-v2-optimization-plan.md` | `docs/plans/moldet-v2-optimization.md` | Recent (2d), design plan |
| `docs/pipeline-redesign.md` | `plans/archived/pipeline-redesign.md` | A1 (33d) |
| `docs/pageindex-research.md` | `docs/research/pageindex-research.md` | Recent research |
| `docs/TECH_STACK.md` | `docs/references/tech-stack.md` | Reference |
| `docs/REFERENCES.md` | `docs/references/README.md` | Reference index |
| `docs/rig_api_surface.md` | `docs/references/rig-api-surface.md` | Reference |
| `docs/specs/llm-chemical-extraction-reference.md` | `docs/research/llm-chemical-extraction-reference.md` | Research, not canonical spec |
| `docs/structure.drawio` | `docs/diagrams/structure.drawio` | Diagram |
| `docs/pdfIO.drawio` | `docs/diagrams/pdfio.drawio` | Diagram |
| `docs/mbforge_introduction_v2.html` | `docs/archive/intro-v2.html` | A2 (82K, 20d, no inbound links) |
| `docs/pdf-pipeline-test/` | `docs/research/pdf-pipeline-test/` | Test fixtures for design research |

### 5.4 `ref/` script/code helpers → `scripts/`

| From | To | Reason |
|---|---|---|
| `ref/migrate_to_rig.py` | `scripts/migrate_to_rig.py` | Code helper |
| `ref/gen_closure_tools.py` | `scripts/gen_closure_tools.py` | Code helper |
| `ref/pull-all.py` | `scripts/pull-all.py` | Code helper |
| `ref/pull-all.ps1` | `scripts/pull-all.ps1` | Code helper |
| `ref/_test_gen.py` | *(delete)* | Throwaway test helper (306B) |
| `ref/INDEX.md` | `docs/references/external-index.md` | Reference index |
| `ref/mineru-popo.md` | `docs/references/external/mineru-popo.md` | External note |
| `ref/molecode.md` | `docs/references/external/molecode.md` | External note |
| `ref/harness-systems.md` | `docs/references/external/harness-systems.md` | External note |
| `ref/harness-engineering.md` | `docs/references/external/harness-engineering.md` | External note |
| `ref/wiki-app-notes.md` | `docs/references/external/wiki-app-notes.md` | External note |
| `ref/chematic.md` | `docs/references/external/chematic.md` | External note |
| `ref/memvid.md` | `docs/references/external/memvid.md` | External note |

### 5.5 `ref/` external materials → `reference/`

All of the following move to `reference/`:

| Source | Destination |
|---|---|
| `ref/literature/` | `reference/literature/` |
| `ref/MolDetect/` | `reference/MolDetect/` |
| `ref/PocketXMol/` | `reference/PocketXMol/` |
| `ref/MoleCode/` | `reference/MoleCode/` |
| `ref/chematic/` | `reference/chematic/` |
| `ref/GESim/` | `reference/GESim/` |
| `ref/paddleocr-vl-local/` | `reference/paddleocr-vl-local/` |
| `ref/MolScribe/` | `reference/MolScribe-ref/` |
| `setup/MolScribe/` | `reference/MolScribe-setup/` |
| `ref/PatSight - Streamlining Patent Analysis To Jump-Start Your Drug Discovery.mhtml` | `reference/PatSight-Streamlining-Patent-Analysis.mhtml` |
| `ref/CN120118069A.PDF` | `reference/CN120118069A.PDF` |
| `ref/US20260027089A1.PDF` | `reference/US20260027089A1.PDF` |

### 5.6 Files that stay unchanged

- `AGENTS.md`, `CLAUDE.md`, `README.md`, `LICENSE`, `.env.template`, `.gitignore`, `.editorconfig`
- `pyproject.toml`, `uv.lock`
- `frontend/`, `src-tauri/`, `src/`, `tests/`
- `setup/modules/`, `setup/{index.bat,index.sh,common.sh,setup_molscribe.py,download_molscribe.py,README.md}`
- `archived/agent/`
- `docs/specs/` (canonical specs — except `llm-chemical-extraction-reference.md` per 5.3)
- `docs/superpowers/` (auto-generated, KEEP path)
- `.claude/`, `skills/`, `.tmp/`, `.ruff_cache/`

## 6. Link Audit Scope

Post-migration, run `skills/doc-audit/scripts/scan_dead_refs.py` and fix any links in:

- `AGENTS.md` (24+ internal refs)
- `CLAUDE.md`
- `docs/specs/README.md`, `docs/specs/architecture-conventions.md`
- `plans/*.md`, `plans/archived/*.md`
- `README.md`
- `setup/README.md`, `setup/setup_molscribe.py`
- Rust source comments referencing doc paths

Frontend/Rust/Python source files: no doc references expected; IPC types unchanged.

## 7. Side Effects

1. `constants.yaml` move breaks `scripts/generate_constants.py` if it hardcodes root path → must update generator script's `--source` argument (or make it positional).
2. `docs/archive/` is a NEW dir; spec needs at least one file (`intro-v2.html`) so the path is "owned".
3. `reference/` replaces `ref/` — `git mv` is used but old `ref/` directory must be removed (verified empty).
4. `plans/archived/` is NEW; same as 7.2.

## 8. Governance Doc

Create `.claude/documentation-governance.md` (currently referenced in CLAUDE.md as if it exists but doesn't). Contents:

- Three-zone model summary
- Archive rules (A1-A4)
- "Where does X go?" decision tree:
  - Compiles/runs → `code/`
  - Dated task plan → `plans/`
  - Stale plan → `plans/archived/`
  - Canonical spec → `docs/specs/`
  - Auto-generated design plan → `docs/superpowers/`
  - One-off investigation → `docs/research/`
  - API/tech surface → `docs/references/`
  - Review/audit → `docs/audit/`
  - Diagram → `docs/diagrams/`
  - HTML presentation → `docs/visuals/`
  - External reference → `reference/`
  - Cross-language config → `configs/`

## 9. AGENTS.md Update

Rewrite the "Key Directories" section in `AGENTS.md` to match the new layout. Keep `Architecture & Data Flow` table intact (it's about code paths, which haven't moved).

## 10. Verification Plan

After migration:

1. `cd src-tauri && cargo check` — Rust still compiles (no code paths changed).
2. `cd frontend && npx tsc --noEmit` — TS still type-checks.
3. `uv run ruff check src/ && uv run ruff format src/ --check` — Python lint/format clean.
4. Run `skills/doc-audit/scripts/scan_dead_refs.py` and confirm 0 broken links.
5. `rtk git ls-files | wc -l` should match pre-move count minus deletes (`reasonix.toml` is gitignored and was never tracked; `_test_gen.py` was tracked, +1 removed).
6. `rtk git status` clean.

## 11. Open Follow-ups (out of scope)

- Dedupe `reference/MolScribe-ref/` vs `reference/MolScribe-setup/` (single source of truth).
- Decide whether `setup/setup_molscribe.py` should symlink or copy `reference/MolScribe-setup/`.
- Whether `docs/visuals/` survives as an empty dir or is removed until needed. If no file lands there in this migration, do not create the empty dir.
