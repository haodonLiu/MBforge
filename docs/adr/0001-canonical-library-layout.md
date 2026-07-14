# ADR 0001: Canonical library layout and root terminology

- **Status**: Accepted (Phases 0–4 largely landed; Phase 6 cleanup still open for
  legacy fallbacks — see § Migration timeline)
- **Date**: 2026-07-10
- **Last note**: 2026-07-14 — runtime uses `library_root` / `libraryRoot` only;
  unified DB is `{root}/.mbforge/library.db`. Context below is historical
  motivation; **current layout** is §2 as amended by the 2026-07 note.
- **Deciders**: MBForge core team
- **Supersedes**: ad-hoc project/library dual naming

## Context (as of decision date 2026-07-10)

> Snapshot of the problem space when this ADR was written. Several items below
> are **already resolved** in code (compat aliases removed; Dear PyGui gone;
> single DB under `.mbforge/library.db`). Do not re-implement the dual-name
> world described here.

MBForge had accumulated two parallel naming conventions for the same concept
— the on-disk directory a user opens to ingest documents:

- **Backend (Python)**: historically both `project_root` and `library_root`
  appeared in request bodies and pipeline args. Canonical name is now
  **`library_root` only**.
- **Frontend (TypeScript)**: canonical **`libraryRoot`**; do not reintroduce
  `projectRoot`.
- **Disk layout**:
  - Canonical artifacts: `{root}/storage/{doc_id}/` via `ArtifactResolver`.
  - Crops: `{root}/storage/{doc_id}/crops/`; legacy `{root}/.mbforge/crops/`
    is read-only fallback until `scripts/migrate_artifact_paths.py`.
  - DB: **`{root}/.mbforge/library.db`** (unified). Pre-migration libraries may
    still have `index/*.db` until `python -m mbforge.migrate-library`.

Dear PyGui (`src/mbforge/gui/`) was removed; React `frontend/` is the only UI.

## Decision

### 1. Canonical terms (single source of truth)

| Concept | Canonical | Deprecated (do not use in new code) |
|---|---|---|
| User's library directory (Python) | `library_root` | `libraryRoot`, `project_root`, `projectRoot` |
| User's library directory (TS/JSON wire) | `libraryRoot` | `projectRoot`, `project_root` |
| A document inside a library | `doc_id` | — |
| Document artifact directory | `storage/{doc_id}/` | `.mbforge/crops/{doc_id}/` (legacy crops read fallback) |

All new code MUST use the canonical names. Review must reject new deprecated aliases.

### 2. Layout ownership (current)

| Path | Owned by | Contents |
|---|---|---|
| `{root}/.mbforge/library.db` | `core/database.py` + `LibraryLayout.database_path` | unified business + molecule DB |
| `{root}/.mbforge/` | internal metadata | library-internal state; not user-edited |
| `{root}/.mbforge/openkb/` | OpenKB + PageIndex | tree index + wiki + dense-rerank cache |
| `{root}/storage/{doc_id}/` | `ArtifactResolver` | `source.pdf`, `reorganized.md`, `indexed.md`, `report.json`, `pages/`, `crops/` |
| `{root}/notes/` | notes feature | user-authored notes |
| `{root}/index/*.db` | **legacy only** | pre-unification DBs; migrate via `python -m mbforge.migrate-library` |

`.mbforge/` is internal metadata only — never visible to the user, never
referenced from request payloads, never the source of a "primary artifact".
If something needs to be user-visible, it lives in `storage/{doc_id}/` or
in a future `notes/`, not in `.mbforge/`.

### 3. Path resolution: two classes, no inline joins

- **`LibraryLayout`** (Phase 2) owns library-level paths: `metadata_dir`,
  `database_path`, `openkb_dir`, `notes_dir`, `migration_dir`. It is the
  only place that constructs `{root}/index`, `{root}/.mbforge`, etc.
- **`ArtifactResolver`** owns document-level paths inside `storage/{doc_id}/`:
  `source_pdf(doc_id)`, `reorganized_md(doc_id)`, `crop(doc_id, relpath)`,
  `pages_dir(doc_id)`. It validates `doc_id` against `_SAFE_DOC_ID_RE`
  and raises `PathTraversalError` (status 403, error_code
  `path_traversal`) on traversal attempts.

No module is allowed to construct these paths inline. `rg ' / "index"| / "\.mbforge"| / "storage"' src/mbforge` after Phase 2 must only match
`LibraryLayout`, `ArtifactResolver`, migration modules, and their tests.

### 4. Single official client: React frontend

MBForge has exactly one official user interface: the React 19 + Vite 8
SPA in `frontend/`. The `src/mbforge/gui/` Dear PyGui shell is removed
(see Phase 0.3 of the path-migration plan). `python -m mbforge` boots
the FastAPI server and auto-opens the React page in the default browser
(unless `--no-browser` is set or the env `MBFORGE_NO_BROWSER=1`). A
future "native window" shell, if ever needed, wraps the already-built
React bundle via WebView — it does not reimplement document, molecule,
or queue UIs.

### 5. No `entity_id` indirection

Some prior art proposed an `entity_id` layer to abstract "thing in
storage". We reject that. The doc_id is the entity_id — every artifact
lives under `storage/{doc_id}/` and every SQLite row references the
doc by its doc_id (or by canonical_smiles for molecules). Adding an
`entity_id` layer would split identity from artifact location and
introduce a translation map that has to stay in sync with the file
system. The current arrangement (one row per canonical concept, one
directory per doc) is the simplest model that supports the read/write
workload.

## Consequences

### Positive

- One name per concept across backend, frontend, wire, and disk. The next
  reader can grep `library_root` and find every call site, every test,
  every doc reference, without deduping aliases.
- `ArtifactResolver` is already the single authority for document paths
  and the only file that knows the `storage/{doc_id}/` layout. Phase 2
  extends that authority to library-level paths via `LibraryLayout`.
- The `.mbforge/` dir becomes a true "do not touch" zone. Users who
  hand-edit it get warned; tests that assert against it get a marker.
- Removing `src/mbforge/gui/` drops dearpygui from `pyproject.toml`
  (saves install time and a heavyweight GUI dep that pulled in
  glfw/cython transitive deps).
- No `entity_id` indirection: there is no abstract "thing" layer to
  keep consistent with the filesystem. The doc_id IS the storage
  namespace.

### Negative / risks

- The frontend `projectRoot` sweep touches ≈300 call sites. A
  search-and-replace risk is calling the wrong field at a component
  boundary. Mitigation: a TypeScript type `LibraryRootContextValue`
  narrows the context to `libraryRoot` only, so any old call site that
  re-introduces `projectRoot` fails the typecheck.
- Removing `src/mbforge/gui/` is a one-way door. Any user who scripted
  `--gui` will see their command fail. Mitigation: surface a
  `DeprecationWarning` in the current `__main__.py` for one release
  before removing (already shipped in commit `f5df8eb` line for
  `__main__.py: gui_mode`).
- `LibraryLayout` is a new abstraction. If a Phase 2 path slips through
  the new constraint, the cleanup loop in Phase 6 will catch it; we
  pay the cost of a second cleanup pass to keep Phase 2 small.

## Migration timeline

- **Phase 0** (this ADR + 2026-07-10): nail the canonical names, write
  the ADR, unblock `npm run build`, kill the dead Dear PyGui shell.
- **Phase 1** (this ADR + 2026-07-10): backend param rename to
  `library_root`, frontend param rename to `libraryRoot`, deprecation
  warning on each compat alias hit. `resolve_root()` stays as a
  shim.
- **Phase 2** (next): introduce `LibraryLayout`. Replace all
  `Path(root) / "index"` / `Path(root) / ".mbforge"` constructions
  with `LibraryLayout` calls. ArtifactResolver continues to own
  document-level paths.
- **Phase 4** (separate commit, separate test, separate release per the
  plan): single-DB migration to `{root}/.mbforge/library.db`.
- **Phase 6** (after one release cycle of no migration failures):
  remove `project_root` / `projectRoot` input compat, remove
  `index/*.db` runtime fallback, remove `.mbforge/crops/` read
  fallback, remove the GUI/MolDet shims.

## References

- `src/mbforge/core/layout.py:LibraryLayout` — library-level paths (current)
- `src/mbforge/core/artifact.py:ArtifactResolver` — document-level paths
- `src/mbforge/core/database.py:DatabaseManager` — unified `.mbforge/library.db`
  (+ legacy `index/*.db` fallback until migration)
- `scripts/migrate_artifact_paths.py` — crops path migration
- `python -m mbforge.migrate-library` — library DB unification
- `docs/specs/architecture-conventions.md` — architecture overview
- `docs/architecture/pipeline-stages.md` — pipeline + storage summary
- `AGENTS.md` / `CLAUDE.md` — AI-facing summaries of canonical names
