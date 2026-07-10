# ADR 0001: Canonical library layout and root terminology

- **Status**: Accepted
- **Date**: 2026-07-10
- **Deciders**: MBForge core team
- **Supersedes**: ad-hoc project/library dual naming

## Context

MBForge has accumulated two parallel naming conventions for the same concept
— the on-disk directory a user opens to ingest documents:

- **Backend (Python)**: both `project_root` and `library_root` are accepted
  in HTTP request bodies, in Pydantic request models, in pipeline runner
  arguments, and in agent tool arguments. The single source of truth is
  `mbforge.utils.helpers.resolve_root()`, which checks `library_root`,
  `libraryRoot`, `project_root`, `projectRoot` in priority order and falls
  back to `load_global_config().library_root`.
- **Frontend (TypeScript)**: the canonical name in `AppContext.tsx` is
  `libraryRoot`, but ≈300 call sites still use `projectRoot` / `project_root`.
  These legacy names work because the backend compat layer accepts both,
  but the divergence is a footgun (different call sites reading the same
  context can see different field names).
- **Disk layout**: the storage layer is also bifurcated:
  - `src/mbforge/core/artifact.py:ArtifactResolver` writes canonical artifacts
    to `{root}/storage/{doc_id}/` (source PDF, reorganized markdown, indexed
    markdown, report.json, page texts, crops).
  - Older code wrote crops to `{root}/.mbforge/crops/{doc_id}/`. The
    `scripts/migrate_artifact_paths.py` migration moves them and rewrites
    the `crop_relpath` columns in SQLite.

In addition, MBForge previously offered a Dear PyGui desktop shell
(`src/mbforge/gui/`) in parallel with the React frontend. That shell is
zero-importer dead code as of 2026-07-08 and confuses the architecture story.

## Decision

### 1. Canonical terms (single source of truth)

| Concept | Canonical | Deprecated (allowed only as compat input) |
|---|---|---|
| User's library directory (Python) | `library_root` | `libraryRoot`, `project_root`, `projectRoot` |
| User's library directory (TS/JSON wire) | `libraryRoot` | `projectRoot`, `project_root` |
| A document inside a library | `doc_id` | (none — already canonical) |
| Document's on-disk artifact directory | `storage/{doc_id}/` | `.mbforge/crops/{doc_id}/` (legacy crops) |

All new code MUST use the canonical names. New call sites that introduce
deprecated names will be rejected in code review.

### 2. Layout ownership

| Path | Owned by | Contents |
|---|---|---|
| `{root}/index/*.db` | `src/mbforge/core/database.py` (current) | `knowledge_base.db`, `molecules.db` (FTS5 + evidence + relations) |
| `{root}/.mbforge/` | internal metadata dir | reserved for library-internal state; users do not edit this directly |
| `{root}/storage/{doc_id}/` | `src/mbforge/core/artifact.py:ArtifactResolver` | `source.pdf`, `reorganized.md`, `indexed.md`, `report.json`, `pages/{n:04d}.txt`, `crops/{filename}.png` |
| `{root}/openkb/` | OpenKB + PageIndex (third-party) | vectorless tree + dense rerank index |
| `{root}/notes/` | user-editable notes dir | user-authored notes (Phase 5 work) |

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

- `src/mbforge/utils/helpers.py:resolve_root()` — current compat layer
- `src/mbforge/core/artifact.py:ArtifactResolver` — document-level paths
- `src/mbforge/core/database.py:DatabaseManager` — index/*.db layout
- `scripts/migrate_artifact_paths.py` — pre-canonical crops migration
- `AGENTS.md` — "Field name deprecations" section (this ADR is the
  authoritative expansion of that table)
- `docs/specs/architecture-conventions.md` — architecture overview
- The 6-phase path-migration plan (user attachment, 2026-07-10)
