# MBForge Unified Refactoring Plan

**Date**: 2026-06-08
**Sources**: Codex audit, Kimi audit, CodeGraph verification (5658 nodes, 11900 edges, 396 files)
**Architecture preserved**: Rust main + Python sidecar (FastAPI:18792) + TypeScript frontend (Tauri v2)

---

## Table of Contents

- [1. Consolidated Findings Matrix](#1-consolidated-findings-matrix)
- [2. Verification Summary](#2-verification-summary)
- [3. Phase 0: Quick Wins (1-2 days)](#3-phase-0-quick-wins)
- [4. Phase 1: Dead Code + Duplicate Elimination (3-5 days)](#4-phase-1-dead-code--duplicate-elimination)
- [5. Phase 2: DB Connection Unification (5-8 days)](#5-phase-2-db-connection-unification)
- [6. Phase 3: Sidecar HTTP + Embedder Consolidation (3-5 days)](#6-phase-3-sidecar-http--embedder-consolidation)
- [7. Phase 4: Agent Tool Registry + Parser LLM Gateway (5-8 days)](#7-phase-4-agent-tool-registry--parser-llm-gateway)
- [8. Phase 5: Error Handling + Test Coverage (ongoing)](#8-phase-5-error-handling--test-coverage)
- [9. Phase 6: Config Unification + Frontend Cleanup (3-5 days)](#9-phase-6-config-unification--frontend-cleanup)
- [10. Risk Matrix](#10-risk-matrix)
- [11. Rollback Strategies](#11-rollback-strategies)
- [12. Excluded / Rejected Findings](#12-excluded--rejected-findings)

---

## 1. Consolidated Findings Matrix

Each finding from all three sources has been cross-verified against CodeGraph evidence.

| # | Finding | Codex | Kimi | CodeGraph | Verdict | Priority | Phase |
|---|---------|-------|------|-----------|---------|----------|-------|
| F01 | `mol_store.rs` == `molecule_store.rs` (dead duplicate) | P0 | -- | CONFIRMED: mol_store.rs active (registered L103-113), molecule_store.rs dead (not in mod.rs) | CONFIRMED | P0 | 0 |
| F02 | `mol_engine.rs` == `molecule_engine.rs` (dead duplicate) | P0 | -- | CONFIRMED: mol_engine.rs active (main.rs:12 imports), molecule_engine.rs only consumed by dead molecule_store.rs | CONFIRMED | P0 | 0 |
| F03 | `core/molecule/sar_query.rs` == `core/chem/sar_query.rs` (dead copy) | -- | -- | CONFIRMED: molecule/mod.rs does NOT declare `pub mod sar_query`; only chem/mod.rs does. Dead file. | CONFIRMED | P0 | 0 |
| F04 | `arxiv.rs` vs `arxiv_rig.rs` duplicate | P0 | -- | REJECTED: Two adapters for different agent frameworks (legacy ReAct vs rig). Complementary, not duplicate. | REJECTED | -- | -- |
| F05 | Three memory modules duplicate | P0 | -- | PARTIALLY_CONFIRMED: memory.rs = legacy user-profile (still active for persona injection), managed_memory.rs+compactor.rs = active rig ConversationMemory. Complementary systems. Legacy memory.rs should be migrated to rig MemoryManager interface. | PARTIALLY_CONFIRMED | P2 | 4 |
| F06 | Two agent tool systems | P0 | -- | REJECTED: No core/executor/ directory exists. executor_rig.rs is a clean adapter layer over native fs/kb/document/molecule.rs. Single system. | REJECTED | -- | -- |
| F07 | Module layout half-flat half-grouped | P1 | -- | CONFIRMED: core/mod.rs has ~65 lines of `pub use` re-exports creating dual import paths (e.g., `core::molecule_store` vs `core::molecule::molecule_store`). | CONFIRMED | P1 | 1 |
| F08 | Commands naming chaos | P1 | -- | CONFIRMED: commands/mod.rs has mol_store, mol_engine (old names) alongside molecule, molecode (new names). 4 dead files on disk. | CONFIRMED | P0 | 0 |
| F09 | Frontend dual API layer | P1 | -- | CONFIRMED: client.ts (157 lines) still active with 2 direct importers (MoleculeDisplay, CorrectionPanel). validateSmiles in client.ts and chemValidateSmiles in tauri/molecule.ts call same Rust command. SAR types duplicated between client.ts and tauri/sar.ts. | CONFIRMED | P1 | 6 |
| F10 | Core calls sidecar HTTP directly | P2 | -- | CONFIRMED: sidecar_url() is called as a function from constants.rs in molecule_engine.rs:207; threaded as &str param through 15+ call sites. Inconsistent pattern. | CONFIRMED | P2 | 3 |
| F11 | Embedder bypasses shared HTTP pool | P2 | -- | CONFIRMED: SidecarEmbedder builds its own reqwest::blocking::Client (embedding.rs:86-93). core/http.rs provides async clients. Blocking vs async type mismatch prevents direct reuse. | CONFIRMED | P2 | 3 |
| F12 | MoleculeEngineState single-instance trap | P2 | -- | CONFIRMED: get_or_init_engine() returns Ok(()) if already initialized regardless of project_root. No re-init command exists. Silent wrong-project operation on switch. | CONFIRMED | P1 | 1 |
| F13 | Pipeline.rs bloat | P2 | -- | REJECTED: pipeline.rs is a module root (2018 lines, ~700+ are tests). The 58 symbols include PipelineOutput enum + 4 Tauri commands. Not a monolith. | REJECTED | -- | -- |
| F14 | Chem facade unused | P2 | -- | CONFIRMED: chem_facade.rs defines 4 wrappers; zero callers across entire codebase. Parsers call core::chem::chem and core::chem::markush directly. | CONFIRMED | P0 | 0 |
| F15 | DB connection fragmentation | -- | Root 1 | CONFIRMED: 8+ independent Connection::open call sites. knowledge_base.rs opens 3 connections to same file. semantic_cache.rs opens ephemeral connections per operation + spawns threads that each open their own. | CONFIRMED | P1 | 2 |
| F16 | Parsers reverse dependency | -- | Root 2 | CONFIRMED: post_process.rs:386 dispatch_chat() creates rig-core OpenAiClient/AnthropicClient per call. call_llm_api() creates new tokio runtime per call (line 368). Duplicates provider setup from rig_adapter.rs. | CONFIRMED | P2 | 4 |
| F17 | Sidecar HTTP scattered across 3 layers | -- | Root 3 | CONFIRMED: sidecar_url threaded as &str through 15+ functions. Some callers pass as param, some call constants::sidecar_url() directly, one accepts but ignores it (molecule_dedup.rs). | CONFIRMED | P2 | 3 |
| F18 | Agent tool registration hardcoded | -- | Root 4 | CONFIRMED: assemble_rig_tool_vec() at rig_adapter.rs:679-710 has 25 sequential push calls. Adding a tool requires editing this function + importing the struct. | CONFIRMED | P2 | 4 |
| F19 | No storage abstraction | -- | Root 5 | PARTIALLY_CONFIRMED: FileCache accepts injected Connection (good pattern). KnowledgeBase opens its own. No fs::write abstraction but file writes are limited to specific modules. | PARTIALLY_CONFIRMED | P3 | 6 |
| F20 | 414 unwrap/expect/panic in production | -- | -- | CONFIRMED (deep dive): Top offenders: molecule_store.rs (64), ingest_queue.rs (39), pipeline.rs (36), conversation_store.rs (25). AppError exists but underused. | CONFIRMED | P1 | 5 |
| F21 | 26 core modules lack inline tests | -- | -- | CONFIRMED (deep dive): executor_rig.rs (149 symbols), knowledge_base.rs (42), molecule_db.rs (38), llm_client.rs (12) all untested. | CONFIRMED | P1 | 5 |
| F22 | Python sidecar no graceful shutdown | -- | -- | CONFIRMED: main.py lifespan has no post-yield cleanup. health.py calls get_embedder/get_reranker/get_vlm every 5s with no circuit breaker. | CONFIRMED | P2 | 3 |
| F23 | Process-level singletons bypass Tauri lifecycle | -- | -- | CONFIRMED: SIDECAR_CHILD_SLOT (OnceLock), KB_CACHE+SEMANTIC_CACHE (OnceLock DashMap), PDF_HASH_CACHE (LazyLock Mutex HashMap). No eviction, no reset. | CONFIRMED | P2 | 2 |
| F24 | Constants duplicated Rust/Python | -- | -- | CONFIRMED: constants.rs says "Keep in sync with constants.py" manually. settings.rs ModelConfig::default() hardcodes max_tokens=4096 instead of referencing LLM_MAX_TOKENS. | CONFIRMED | P2 | 6 |
| F25 | post_process.rs creates new tokio runtime per LLM call | -- | -- | CONFIRMED (deep dive): call_llm_api() line 368 creates tokio::runtime::Builder::new_current_thread() per invocation. Called in loop from post_process() lines 771-807. | CONFIRMED | P2 | 4 |

---

## 2. Verification Summary

| Source | Total Claims | Confirmed | Partially Confirmed | Rejected |
|--------|-------------|-----------|---------------------|----------|
| Codex | 13 | 8 | 1 | 4 |
| Kimi | 5 | 5 | 0 | 0 |
| Deep dive (new) | 5 | 5 | 0 | 0 |
| **Total** | **23** | **18** | **1** | **4** |

Rejected findings and reasons:
- **F04 (arxiv dual)**: Two adapters for different agent frameworks -- legitimate separation
- **F06 (two tool systems)**: No core/executor/ directory exists; executor_rig.rs is a clean adapter layer
- **F13 (pipeline bloat)**: Module root with tests, not a monolith; 2018 lines is reasonable
- **F05 (memory triple)**: Complementary systems (legacy user-profile + active rig ConversationMemory), not duplicates

---

## 3. Phase 0: Quick Wins

**Effort**: 1-2 days | **Risk**: Very Low | **Test changes**: None (removing dead code)

These are pure deletions of dead files with zero callers. No behavioral change.

### 3.1 Delete dead command files

**Files to delete**:
- `src-tauri/src/commands/molecule_store.rs` -- byte-identical to mol_store.rs, NOT registered in mod.rs
- `src-tauri/src/commands/molecule_engine.rs` -- byte-identical to mol_engine.rs, only consumed by dead molecule_store.rs

**Verification**: `commands/mod.rs` lines 8-9 register `mol_engine` and `mol_store` (the active files). The `molecule_*` variants are never compiled.

### 3.2 Delete dead chem duplicate

**File to delete**:
- `src-tauri/src/core/molecule/sar_query.rs` -- byte-identical to `core/chem/sar_query.rs`, NOT declared in `core/molecule/mod.rs`

### 3.3 Delete unused chem facade

**File to delete**:
- `src-tauri/src/core/chem/chem_facade.rs` -- 4 wrapper functions with zero callers

**Follow-up**: Remove `pub mod chem_facade;` from `core/chem/mod.rs` if declared.

### 3.4 Remove dead client_120s() from http.rs

**File**: `src-tauri/src/core/http.rs`
- `client_120s()` has zero callers. Remove the function and its LazyLock.

### Rollback

Git revert of the single commit. All removed files are dead code with zero compile-time consumers.

---

## 4. Phase 1: Dead Code + Duplicate Elimination

**Effort**: 3-5 days | **Risk**: Low | **Test changes**: Rename tests to match new module names

### 4.1 Remove backward-compat re-exports from core/mod.rs

**Current state**: `core/mod.rs` has ~65 lines of `pub use` re-exports (lines 17-83) that create dual import paths. For example:
- `core::molecule_store::MoleculeRecord` (via re-export) resolves to
- `core::molecule::molecule_store::MoleculeRecord` (canonical path)

**Action**:
1. Run `grep -rn 'crate::core::molecule_store\|crate::core::molecule_engine\|crate::core::molecule_db\|crate::core::molecule_dedup\|crate::core::molecule_cluster' src-tauri/src/` to find all old-path importers
2. For each hit, update to canonical sub-module path (e.g., `crate::core::molecule::molecule_store::MoleculeRecord`)
3. Remove the corresponding `pub use` lines from `core/mod.rs`
4. Keep the re-exports that are genuinely needed for frequently-used types (e.g., `pub use molecule::molecule_store::{MoleculeDatabase, MoleculeRecord}` is fine as a convenience if all callers are migrated)

**Affected files** (known importers of old paths):
- `commands/mol_store.rs` -- uses `crate::core::molecule_store::MoleculeRecord`
- `parsers/pipeline/helpers.rs` -- uses old molecule_store path
- `parsers/pipeline.rs` -- uses old molecule_store path

### 4.2 Fix MoleculeEngineState single-instance trap

**Current state**: `get_or_init_engine()` at `commands/mol_engine.rs:34` does `if guard.is_some() { return Ok(()); }` -- once initialized, the engine is never replaced regardless of project_root.

**Action**:
1. Change `MoleculeEngineState.inner` from `Arc<AsyncMutex<Option<MoleculeEngine>>>` to `Arc<AsyncMutex<Option<(String, MoleculeEngine)>>>` storing the project_root alongside the engine
2. In `get_or_init_engine()`, compare stored root with requested root; if different, drop old engine and create new one
3. Add a `reinit_engine()` command exposed to frontend for explicit project switching

```rust
// Target implementation sketch:
pub async fn get_or_init_engine(
    state: &MoleculeEngineState,
    project_root: &str,
) -> Result<(), String> {
    let mut guard = state.inner.lock().await;
    if let Some((ref root, _)) = *guard {
        if root == project_root {
            return Ok(());
        }
        // Different project: drop old engine, reinitialize
        log::info!("MoleculeEngine switching from {} to {}", root, project_root);
    }
    let root = PathBuf::from(project_root);
    let engine = MoleculeEngine::new(&root)
        .map_err(|e| format!("MoleculeEngine init failed: {}", e))?;
    *guard = Some((project_root.to_string(), engine));
    Ok(())
}
```

**Affected callers**: 23 call sites across `mol_store.rs`, `molecule.rs`. All pass `project_root` already -- no signature change needed.

### 4.3 Rename commands for consistency

**Action**: After Phase 0 deletes the dead `molecule_store.rs` and `molecule_engine.rs`, the naming is already clean. Document the convention:
- `commands/mol_*.rs` = molecule-related Tauri commands
- `commands/molecule.rs` = molecule relation/cluster/SAR commands

No file renames needed -- the active files are already the canonical ones.

### Test changes

- Update any `use` statements in test files that reference old re-export paths
- Verify `cargo test` passes with ~323 tests

### Rollback

Each sub-step is a separate commit. Revert individual commits if any regression is found. The MoleculeEngineState fix (4.2) has the highest blast radius -- test with project switching before merging.

---

## 5. Phase 2: DB Connection Unification

**Effort**: 5-8 days | **Risk**: Medium | **Test changes**: Add unit tests for connection manager | **Depends on**: Phase 1

### 5.1 Create unified connection manager

**New file**: `src-tauri/src/core/db.rs`

```rust
/// Centralized SQLite connection manager.
/// One Connection per DB file, shared via Arc<Mutex<Connection>>.
pub struct DbManager {
    /// {project_root}/.mbforge/knowledge_base.db
    kb_conn: Arc<Mutex<Connection>>,
    /// {project_root}/.mbforge/molecules.db
    mol_conn: Arc<Mutex<Connection>>,
    /// {project_root}/.mbforge/conversations.db
    conv_conn: Arc<Mutex<Connection>>,
}
```

**Migration plan**:
1. KnowledgeBase currently opens 3 connections to `knowledge_base.db` (vector_store, file_cache, fts_conn) + ingest_queue opens a 4th. Consolidate to 1 connection (WAL mode supports concurrent reads).
2. MoleculeDatabase + MoleculeRelationDb both open connections to `molecules.db`. Consolidate to 1 connection shared via Arc.
3. SqliteConversationMemory opens its own connection -- keep separate (different DB file).
4. SemanticCache opens ephemeral connections per operation + spawns threads that open their own. Refactor to accept an injected connection from DbManager.

### 5.2 Fix SemanticCache connection pattern

**Current state**: `semantic_cache.rs` calls `Connection::open()` in `with_conn()` (line 126), `load_from_db()` (line 157), `flush_to_db()` (line 227), and spawns `std::thread::spawn` threads that each open their own connection (lines 277, 298, 335, 364, 386). This is the worst offender.

**Action**:
1. Change SemanticCache to accept `Arc<Mutex<Connection>>` in constructor
2. Remove all `Connection::open()` calls inside SemanticCache
3. Replace `std::thread::spawn` with `tokio::task::spawn_blocking` for async compatibility
4. If the thread-spawn pattern is needed for background persistence, use a single dedicated connection held by the cache

### 5.3 Unwrap global singletons

**Current state**: `KB_CACHE` and `SEMANTIC_CACHE` are `OnceLock<DashMap>` in `knowledge_base.rs` (lines 392-393). `PDF_HASH_CACHE` is `LazyLock<Mutex<HashMap>>` in `detection_cache.rs` (line 46).

**Action**:
1. Move KB_CACHE and SEMANTIC_CACHE into Tauri state management (`.manage()`) so they participate in Tauri lifecycle
2. This enables programmatic reset on project switch and testability in isolation
3. PDF_HASH_CACHE can stay as LazyLock (bounded by session, low risk) but add a `clear()` method exposed via Tauri command

### Test changes

- Unit test: DbManager opens, returns correct connection for each DB file
- Unit test: SemanticCache uses injected connection, no self-open
- Integration test: Project switch clears KB caches

### Rollback

Phase 2 touches the data layer deeply. Rollback strategy: keep old `::open()` patterns behind a feature flag during migration. Remove flag after 2 releases without issues.

---

## 6. Phase 3: Sidecar HTTP + Embedder Consolidation

**Effort**: 3-5 days | **Risk**: Low-Medium | **Test changes**: Unit tests for SidecarClient | **Depends on**: Phase 2

### 6.1 Create SidecarClient abstraction

**New file**: `src-tauri/src/core/sidecar_client.rs`

```rust
/// Centralized HTTP client for Python sidecar communication.
/// Uses core/http.rs shared clients. Eliminates sidecar_url parameter threading.
pub struct SidecarClient {
    base_url: String,
    client_30s: &'static reqwest::Client,   // for most calls
    client_300s: &'static reqwest::Client,  // for VLM/long operations
}
```

**Migration**:
1. Create SidecarClient wrapping `core/http.rs` shared clients
2. Replace all 15+ `sidecar_url: &str` parameters with `&SidecarClient` or inject via Tauri state
3. Remove unused `_sidecar_url` parameter from `molecule_dedup.rs::run_dedup_batch()`

### 6.2 Convert Embedder to async

**Current state**: `SidecarEmbedder` in `embedding.rs` builds its own `reqwest::blocking::Client` with 120s timeout. Cannot reuse `core/http.rs` async clients due to blocking/async mismatch.

**Action**:
1. Convert `SidecarEmbedder::embed_with_trace()` to async
2. Use `client_120s()` from `core/http.rs` instead of creating own client
3. Callers (KnowledgeBase) already run in async context (Tauri commands), so the conversion propagates naturally
4. If any sync caller remains, wrap with `tokio::task::spawn_blocking`

### 6.3 Add Python sidecar graceful shutdown

**File**: `src/mbforge/model_server/main.py`

**Action**:
1. Add post-yield cleanup in lifespan context manager
2. Add circuit breaker to health endpoint: cache model load status for 30s after failure
3. Log shutdown event for debugging

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... startup ...
    yield
    # Graceful shutdown
    logger.info("Sidecar shutting down, draining connections...")
    # Cancel background tasks, flush caches, etc.
```

### 6.4 Health endpoint circuit breaker

**File**: `src/mbforge/model_server/routers/health.py`

**Action**:
1. Add a module-level `_model_status_cache: dict` with 30s TTL
2. On model load failure, cache the error status
3. Subsequent health checks within 30s return cached error without retrying expensive init
4. This prevents the "every 5s retry" storm when a model consistently fails

### Rollback

SidecarClient is a new abstraction layer. If it causes issues, callers can fall back to direct `sidecar_url()` calls. Keep old pattern behind `#[deprecated]` for one release.

---

## 7. Phase 4: Agent Tool Registry + Parser LLM Gateway

**Effort**: 5-8 days | **Risk**: Medium | **Test changes**: Tool registration tests, LLM gateway tests | **Depends on**: Phase 3

### 7.1 Tool registration via inventory/linkme crate

**Current state**: `assemble_rig_tool_vec()` at `rig_adapter.rs:679-710` has 25 sequential `tools.push()` calls. Adding a tool requires editing this function + importing the struct.

**Option A (recommended)**: Use the `inventory` crate for compile-time tool registration.

```rust
// In each tool file:
inventory::submit! {
    ToolRegistration::new::<GrepSearchTool>()
}

// In rig_adapter.rs:
pub fn assemble_rig_tool_vec(project_root: &str) -> Vec<Box<dyn ToolDyn>> {
    inventory::iter::<ToolRegistration>
        .into_iter()
        .map(|reg| reg.instantiate(project_root))
        .collect()
}
```

**Option B (simpler)**: Keep manual registration but extract to a declarative macro:

```rust
macro_rules! register_tools {
    ($project_root:expr, $($tool:ty),+ $(,)?) => {{
        let mut tools: Vec<Box<dyn ToolDyn>> = Vec::new();
        $(tools.push(Box::new(<$tool>::new($project_root)));)+
        tools
    }};
}
```

**Recommendation**: Start with Option B (lower risk, no new dependency). Migrate to Option A if tool count exceeds 40.

### 7.2 LLM gateway for parsers

**Current state**: `parsers/structure/post_process.rs::dispatch_chat()` (line 386) creates rig-core OpenAiClient/AnthropicClient per call. `call_llm_api()` (line 366) creates a new tokio runtime per call. Each call in the post_process loop builds a new client + HTTP pool.

**Action**:
1. Create `core/agent/llm_gateway.rs` -- a shared async LLM client wrapper
2. Move provider setup (OpenAiClient/AnthropicClient builder) into the gateway, cached per config
3. Expose `llm_gateway.chat(system, user) -> Result<(String, Option<u32>)>` async method
4. Refactor `post_process.rs` to accept `&LlmGateway` instead of creating clients internally
5. Remove per-call tokio runtime creation -- the gateway runs on the existing Tauri async runtime

**Blast radius**: `post_process.rs` is called from `pipeline.rs` which is called from Tauri commands. The async propagation is safe since Tauri commands are already async.

### 7.3 Migrate legacy memory to rig interface

**Current state**: `memory.rs` MemoryManager is a JSON-file-based category memory system still used for user profile/persona injection. `managed_memory.rs` MbforgeManagedMemory is the active rig ConversationMemory.

**Action**:
1. Keep `memory.rs` for now -- it serves a different purpose (user profile) from conversation memory
2. Wrap MemoryManager behind the rig `MemoryManager` trait to unify the interface
3. This is lower priority than the other Phase 4 items

### Test changes

- Unit test: Tool registration macro produces correct tool count
- Unit test: LlmGateway caches provider, reuses across calls
- Integration test: post_process uses shared gateway, no per-call runtime

### Rollback

- Tool registry: Keep old `assemble_rig_tool_vec()` as fallback behind feature flag
- LLM gateway: Keep old `dispatch_chat()` as `#[deprecated]` for one release

---

## 8. Phase 5: Error Handling + Test Coverage

**Effort**: Ongoing (target 2-3 weeks for initial pass) | **Risk**: Low | **Test changes**: Add missing tests

### 8.1 Systematic unwrap replacement

**Strategy**: Prioritize by production impact.

| Priority | Module | unwrap count | Action |
|----------|--------|-------------|--------|
| 1 | molecule_store.rs | 64 | Replace with `?` propagation using AppResult |
| 2 | ingest_queue.rs | 39 | Replace with `?` propagation |
| 3 | pipeline.rs | 36 | Replace with `?` propagation (keep unwraps in test code) |
| 4 | conversation_store.rs | 25 | Already partially done; finish remaining |
| 5 | executor_rig.rs | 16 expect() | Replace `.expect("schema serialization")` with `?` |

**Rule**: `.unwrap()` is acceptable ONLY in:
- `#[cfg(test)]` blocks
- Initialization code where failure is truly unrecoverable (e.g., `LazyLock`)
- After an explicit comment justifying why the value cannot be None/Err

### 8.2 Test coverage for critical modules

**Priority modules to add tests for**:

| Module | Symbols | Why critical |
|--------|---------|-------------|
| executor_rig.rs | 149 | Agent ReAct loop -- the brain |
| knowledge_base.rs | 42 | FTS5 + semantic search |
| molecule_db.rs | 38 | Low-level SQLite molecule operations |
| llm_client.rs | 12 | LLM HTTP communication |
| molecule_dedup.rs | 10 | Deduplication logic |
| molecule_cluster.rs | 9 | Clustering |

**Target**: Each module gets at minimum:
- Happy path test
- Error/edge case test
- Round-trip test (write then read back)

### Rollback

Error handling changes are additive (replacing unwrap with ?). If a regression is found, the specific function can be reverted. Test additions are purely additive.

---

## 9. Phase 6: Config Unification + Frontend Cleanup

**Effort**: 3-5 days | **Risk**: Low | **Test changes**: Frontend unit tests

### 9.1 Single source of truth for constants

**Current state**: `constants.rs` says "Keep in sync with constants.py" manually. `settings.rs` ModelConfig::default() hardcodes max_tokens=4096 instead of referencing LLM_MAX_TOKENS.

**Action**:
1. Generate Python constants from the same `constants.yaml` that generates Rust constants
2. Add a build step: `python scripts/gen_constants.py` that reads constants.yaml and emits `src/mbforge/utils/constants.py`
3. Update `settings.rs` to reference constants instead of hardcoding values

### 9.2 Frontend API consolidation

**Current state**: `client.ts` (157 lines) is still active with 2 direct importers. `validateSmiles` in client.ts and `chemValidateSmiles` in tauri/molecule.ts call the same Rust command.

**Action**:
1. Move `validateSmiles` from `client.ts` to `tauri/molecule.ts` (it already has `chemValidateSmiles`)
2. Update MoleculeDisplay.tsx and CorrectionPanel.tsx imports
3. Move `fetchJson`/`sseStream` from client.ts to a shared utility
4. Remove duplicate SAR types from client.ts (use tauri/sar.ts types exclusively)
5. Delete `client.ts` when empty
6. Delete `tauri-bridge.ts` (thin re-export barrel with no unique exports)

### 9.3 AppContext localStorage safety

**File**: `frontend/src/context/AppContext.tsx`

**Action**: Wrap `localStorage.setItem` in try-catch for quota exceeded errors. Trivial change.

### Rollback

Frontend changes are isolated from Rust backend. Revert individual file changes if UI breaks.

---

## 10. Risk Matrix

| Phase | Risk Level | Blast Radius | Mitigation |
|-------|-----------|-------------|------------|
| 0 (Quick Wins) | Very Low | 0 (dead code) | Git revert |
| 1 (Dead Code) | Low | ~10 files (import paths) | Compile-time verification |
| 2 (DB Unification) | Medium | ~15 files (all DB consumers) | Feature flag, staged rollout |
| 3 (Sidecar HTTP) | Low-Medium | ~15 files (sidecar callers) | Keep old pattern deprecated |
| 4 (Tool Registry + LLM) | Medium | Agent loop + parser pipeline | Feature flag, A/B test |
| 5 (Error Handling) | Low | Per-function, isolated | Git revert per function |
| 6 (Config + Frontend) | Low | Frontend only, no Rust impact | Standard frontend testing |

---

## 11. Rollback Strategies

### Per-phase rollback

Each phase produces a single PR. If any phase causes issues:
1. `git revert <merge-commit>` for the phase PR
2. Phase 0: Zero risk rollback (dead code only)
3. Phase 2: If DB unification causes connection issues, re-enable old `::open()` patterns via feature flag `legacy-db-connections`
4. Phase 4: If tool registry breaks agent, fall back to old `assemble_rig_tool_vec()` via feature flag `legacy-tool-vec`

### Cross-phase dependencies

```
Phase 0 ─── no dependencies, can deploy immediately
Phase 1 ─── depends on Phase 0 (dead files removed)
Phase 2 ─── depends on Phase 1 (clean import paths)
Phase 3 ─── depends on Phase 2 (unified connections)
Phase 4 ─── depends on Phase 3 (shared HTTP client for LLM gateway)
Phase 5 ─── independent, can run in parallel with any phase
Phase 6 ─── independent, can run in parallel with any phase
```

### Emergency procedures

- **Rust compile failure**: `cargo check` is the gate. No phase merges without green `cargo check`.
- **Test regression**: `cargo test` (323 tests) + `uv run pytest tests/` (83 tests) must pass.
- **Frontend breakage**: `cd frontend && npm run build` must succeed. TypeScript catches most issues at compile time.

---

## 12. Excluded / Rejected Findings

| Finding | Source | Rejection Reason |
|---------|--------|-----------------|
| arxiv.rs vs arxiv_rig.rs duplicate | Codex | Two adapters for different agent frameworks (legacy ReAct vs rig). Complementary by design. |
| Two agent tool systems (executor/ vs executor_rig.rs) | Codex | No core/executor/ directory exists. executor_rig.rs is a clean adapter layer over native implementations. Single system. |
| Pipeline.rs bloat (58 symbols) | Codex | Module root with tests. 2018 lines is reasonable for a file that wires 4 submodules + defines PipelineOutput + 4 Tauri commands. |
| Three memory modules duplicate | Codex | Complementary systems: memory.rs = legacy user-profile (still active), managed_memory.rs + compactor.rs = active rig ConversationMemory. |
| Frontend AppContext monolithic | Deep dive | AppContext is minimal (63 lines, 2 state values, 10 consumers). Clean architecture. |

---

## Implementation Order Summary

```
Week 1:  Phase 0 (Quick Wins) + Phase 5 start (error handling in critical modules)
Week 2:  Phase 1 (Dead Code + Import Path Cleanup)
Week 3:  Phase 2 (DB Connection Unification) + Phase 6 (Frontend, parallel)
Week 4:  Phase 3 (Sidecar HTTP Consolidation)
Week 5-6: Phase 4 (Tool Registry + LLM Gateway)
Ongoing: Phase 5 (Error Handling + Test Coverage)
```

Total estimated effort: 3-4 weeks of focused work for one developer, or 2 weeks with two developers working in parallel on independent phases.
