---
name: project-context-bootstrap
description: >
  Bootstrap context for a new MBForge session by reading core project files.
  Quickly orients the agent to the current state of the Rust+Python+React
  codebase, build configuration, and recent git history.
metadata:
  type: skill
  domain: onboarding
  project: MBForge
---

# Project Context Bootstrap

When starting a new session on MBForge, read these files in order to establish project context. This replaces the ad-hoc pattern of reading files one-by-one across multiple turns.

## File Reading Order

### 1. Project Identity & Config (always)

```
CLAUDE.md          → AI coding guidelines + full project index
AGENTS.md          → Agent work norms (already auto-injected)
pyproject.toml     → Python deps, build config, version
```

### 2. Architecture Overview (always)

```
src-tauri/src/commands/mod.rs   → All Tauri IPC commands registered
src/mbforge/server.py           → FastAPI endpoints + sidecar entry
frontend/src/App.tsx            → Frontend routing structure
```

### 3. Recent Activity (always)

```bash
git log --oneline -10           → Recent commits
git status --short              → Uncommitted changes
```

### 4. Session-Specific (on demand)

- If working on parsers: `src-tauri/src/parsers/pipeline.rs`
- If working on agent: `src-tauri/src/core/agent/`
- If working on molecule DB: `src-tauri/src/core/molecule/`
- If working on frontend: `frontend/src/api/tauri/` directory
- If working on Python sidecar: `src/mbforge/backends/`

## Quick Reference

| Layer | Entry Point | Language |
|-------|-------------|----------|
| Frontend UI | `frontend/src/App.tsx` | TypeScript |
| Tauri IPC | `src-tauri/src/commands/mod.rs` | Rust |
| Agent/ReAct | `src-tauri/src/core/agent/` | Rust |
| PDF Parser | `src-tauri/src/parsers/pipeline.rs` | Rust |
| Molecule DB | `src-tauri/src/core/molecule/` | Rust |
| Vector Store | `src-tauri/src/core/vector/` | Rust |
| Python Sidecar | `src/mbforge/server.py` | Python |
| Model Backends | `src/mbforge/backends/` | Python |

## When to Use

- Start of a new session targeting this project
- After long inactivity (files may have changed)
- When switching between major subsystems (e.g., from frontend to Rust core)
