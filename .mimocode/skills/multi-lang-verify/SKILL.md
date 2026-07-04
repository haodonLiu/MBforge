---
name: multi-lang-verify
description: >
  Verify Rust and Python compilation across MBForge's dual-language codebase.
  Runs cargo check for Rust (src-tauri/), py_compile for Python (src/mbforge/),
  and optionally npm build for frontend. Use after any code edit to catch errors
  before they compound.
metadata:
  type: skill
  domain: build-verification
  project: MBForge
---

# Multi-Language Verification

MBForge has a dual-language architecture (Rust + Python + TypeScript). After making code changes, verify compilation across all affected layers before proceeding.

## Verification Steps

### 1. Rust Compilation (always run if Rust files changed)

```bash
cd src-tauri && cargo check --message-format=short 2>&1 | grep -E "warning|error" | head -10
```

- Zero output = clean compile
- If errors found, fix before proceeding
- Warnings are acceptable (`.cargo/config.toml` suppresses them in dev, but `--message-format=short` surfaces them)

### 2. Python Syntax Check (always run if Python files changed)

```bash
cd C:/Users/10954/Desktop/MBForge && python -m py_compile src/mbforge/<changed_file>.py 2>&1
```

- For bulk checks, iterate over changed `.py` files
- Alternatively: `uv run python -c "from mbforge.<module> import *; print('OK')"` to verify imports resolve

### 3. Frontend Type Check (if TypeScript files changed)

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

### 4. Frontend Build (optional, before commit)

```bash
cd frontend && npm run build 2>&1 | tail -5
```

## Decision Flow

```
Files changed?
  ├─ Rust (*.rs) → cargo check
  ├─ Python (*.py) → py_compile or import check
  ├─ TypeScript (*.ts, *.tsx) → tsc --noEmit
  └─ All clean → proceed to next task
```

## When to Use

- After any Edit or Write operation on source files
- Before starting a new task (verify prior changes didn't break anything)
- Before committing changes
- When debugging "it worked before" regressions

## Notes

- Windows encoding: if Python scripts output garbled text, prefix with `import sys; sys.stdout.reconfigure(encoding='utf-8')`
- cargo check on Windows uses `.cargo/config.toml` to suppress warnings; use `--message-format=short` for cleaner output
- The project root is `C:/Users/10954/Desktop/MBForge`
