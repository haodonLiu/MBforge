# MBForge Development Guide

> 本文档为 MBForge 开发者提供完整的开发环境配置、代码规范、调试方法和贡献指南。

**Related Documentation:** [Architecture](ARCHITECTURE.md) · [API Reference](API.md) · [Tech Stack](TECH_STACK.md) · [References](../REFERENCES.md)

---

## 1. Development Environment Setup

### 1.1 Prerequisites

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- Git

### 1.2 Clone & Install

```bash
# Clone repository
git clone https://github.com/your-repo/MBForge.git
cd MBForge

# Install all dependencies (including dev dependencies)
uv sync --dev

# Copy environment template
cp .env.template .env
# Edit .env with your API keys and configuration

# Verify installation
uv run mbforge --version
```

### 1.3 uv Workspace Structure

MBForge uses uv workspace to manage multiple packages:

```
MBForge/
├── src/mbforge/              # Main application
├── setup/
│   ├── openSAR/              # Workspace member: csar package
│   └── UniParser-Tools/      # Workspace member: uniparser-tools package
├── tests/
└── pyproject.toml           # Workspace root
```

`uv sync` installs all workspace members in editable mode.

---

## 2. Running the Application

### 2.1 GUI Mode

```bash
mbforge
# or
uv run mbforge gui

# Open specific project directly
mbforge gui --project ./my-project
```

### 2.2 CLI Mode

```bash
# Initialize a new project
mbforge init ./my-project --name "MyProject"

# Index project files
mbforge index ./my-project

# Help
mbforge --help
```

### 2.3 Python Direct Import

```bash
uv run python -c "from mbforge.core.project import Project; print('OK')"
```

---

## 3. Testing

### 3.1 Run All Tests

```bash
uv run pytest tests/ -v
```

### 3.2 Run Specific Test File

```bash
uv run pytest tests/unit/test_project.py -v
```

### 3.3 Run with Coverage

```bash
uv run pytest tests/ --cov=mbforge --cov-report=html
# Open htmlcov/index.html in browser
```

### 3.4 Test Structure

```
tests/
├── unit/
│   ├── test_project.py       # Project class tests
│   ├── test_knowledge_base.py
│   ├── test_mol_database.py
│   └── ...
└── integration/
    └── ...
```

### 3.5 Writing Tests

Use pytest with `from __future__ import annotations` for forward references.

```python
from __future__ import annotations

import pytest
from pathlib import Path
from mbforge.core.project import Project

class TestProject:
    def test_create_project(self, tmp_path: Path):
        project = Project.create(tmp_path / "test-project", name="Test")
        assert project.name == "Test"
        assert (tmp_path / "test-project" / ".mbforge").exists()

    def test_open_invalid_project(self, tmp_path: Path):
        assert Project.open(tmp_path / "nonexistent") is None
```

---

## 4. Code Quality

### 4.1 Formatting (ruff)

```bash
# Format all source files
uv run ruff format src/

# Check without modifying
uv run ruff format --check src/
```

### 4.2 Linting

```bash
uv run ruff check src/

# Auto-fix safe issues
uv run ruff check --fix src/
```

### 4.3 Type Checking

```bash
uv run mypy src/
```

### 4.4 All Checks (pre-commit)

```bash
# Run all quality checks
uv run ruff format src/ && uv run ruff check src/ && uv run mypy src/
```

---

## 5. Project Architecture Quick Reference

### 5.1 Key Entry Points

| File | Purpose |
|------|---------|
| `src/mbforge/cli.py` | CLI entry point (`mbforge` command) |
| `src/mbforge/app.py` | GUI entry point (`run_app()`) |
| `src/mbforge/__main__.py` | `python -m mbforge` entry |

### 5.2 Module Responsibilities

```
core/       → Data models (Project, KnowledgeBase, MoleculeDatabase)
models/     → AI model abstraction (LLM, Embedder, Reranker, VLM)
parsers/    → PDF parsing and molecule extraction
agent/      → ReAct agent with tool execution
ui/         → PyQt6 GUI components
workflow/   → Extension modules (stubs)
parsers/uniparser/  → UniParser API integration
utils/      → Config, logging, helpers
```

### 5.3 Adding a New Module

1. Create module under appropriate package
2. Add `from __future__ import annotations` at top
3. Use absolute imports within package (`from ..utils import ...`)
4. Export public API in package `__init__.py`
5. Add tests in `tests/unit/`

---

## 6. Debugging

### 6.1 Logging

MBForge uses structured logging via `get_logger()`:

```python
from mbforge.utils.logger import get_logger

logger = get_logger(__name__)

logger.debug("Detailed info: %s", variable)
logger.info("Operation completed")
logger.warning("Something unexpected: %s", value)
logger.error("Failed: %s", error)
```

**Log level control:**
```python
from mbforge.utils.logger import setup_logging
setup_logging(level="DEBUG")  # TRACE, DEBUG, INFO, WARNING, ERROR
```

### 6.2 Debug Mode in GUI

Enable debug logging in settings dialog or via environment:

```bash
MBFORGE_LOG_LEVEL=DEBUG mbforge gui
```

### 6.3 PyCharm/VS Code Debugging

For PyCharm:
1. Run → Edit Configurations
2. Add Python configuration
3. Script path: `src/mbforge/cli.py`
4. Parameters: `gui`
5. Working directory: project root
6. Python interpreter: select uv venv

For VS Code (`.vscode/launch.json`):
```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "MBForge GUI",
            "type": "debugpy",
            "request": "launch",
            "module": "mbforge",
            "args": ["gui"],
            "cwd": "${workspaceFolder}",
            "python": "${workspaceFolder}/.venv/Scripts/python.exe"
        }
    ]
}
```

### 6.4 PDB Debugging

```python
import pdb; pdb.set_trace()
# or
breakpoint()  # Python 3.7+
```

---

## 7. Package Management with uv

### 7.1 Add a Dependency

```bash
# Add to pyproject.toml dependencies
uv add some-package

# Add as dev dependency
uv add --dev some-package
```

### 7.2 Update Dependencies

```bash
# Update all dependencies
uv sync

# Update specific package
uv add --upgrade some-package
```

### 7.3 Lock File

```bash
# Regenerate lock file
uv lock
```

### 7.4 Workspace Member Management

Members are defined in `pyproject.toml`:
```toml
[tool.uv.workspace]
members = ["setup/UniParser-Tools", "setup/openSAR"]
```

---

## 8. Build & Release

### 8.1 Build EXE

```bash
uv run python build.py
```

This runs PyInstaller with `MBForge.spec` configuration.

### 8.2 Manual PyInstaller

```bash
uv run pyinstaller MBForge.spec
# Output in dist/
```

### 8.3 Version Bump

Update version in `pyproject.toml`:
```toml
[project]
version = "0.2.0"
```

---

## 9. Contributing Guidelines

### 9.1 Branch Naming

- `feature/` — new features (e.g., `feature/new-molecule-search`)
- `fix/` — bug fixes (e.g., `fix/pdf-parser-crash`)
- `refactor/` — code refactoring
- `docs/` — documentation only

### 9.2 Commit Messages

Follow conventional commits:

```
feat: add substructure search tool
fix: correct SMILES parsing for aromatic rings
docs: update API documentation
refactor: extract tool registry into separate module
test: add KnowledgeBase search tests
```

### 9.3 Pull Request Process

1. Fork and create feature branch
2. Run all checks: `ruff format && ruff check && mypy && pytest`
3. Write/update tests for new functionality
4. Update documentation (README, API docs, CLAUDE.md) if needed
5. Submit PR with clear description

### 9.4 Code Review Checklist

- [ ] All new code has type annotations
- [ ] Docstrings on public classes and functions
- [ ] Tests cover new functionality
- [ ] No `print()` statements (use logger)
- [ ] No hardcoded paths or secrets
- [ ] Error handling for edge cases

---

## 10. File Organization Conventions

### 10.1 Import Order

```python
from __future__ import annotations

# Standard library
import json
from pathlib import Path
from typing import Dict, List, Optional

# Third-party
import chromadb

# Local application
from .base import BaseLLM
from ..utils.config import AppConfig
```

### 10.2 Class Definition Order

```python
class MyClass:
    # Class-level attributes / dataclass fields
    DEFAULT_VALUE = "..."

    # Constructor
    def __init__(self, ...):
        ...

    # Public methods
    def public_method(self, ...):
        ...

    # Properties
    @property
    def something(self):
        ...

    # Private methods (prefixed with _)
    def _private_method(self, ...):
        ...

    # Dunder methods
    def __repr__(self):
        ...

    # Static/class methods
    @classmethod
    def from_dict(cls, data):
        ...
```

### 10.3 Type Hints

- Use `List`, `Dict`, `Optional` from `typing` (not `list[]`, `dict[]`)
- Use `from __future__ import annotations` for forward references
- Use `pathlib.Path` for file paths (not strings)

---

## 11. Common Tasks

### 11.1 Add a New CLI Command

In `cli.py`:

```python
# Add subparser
my_parser = subparsers.add_parser("mycommand", help="My command")
my_parser.add_argument("path", type=str, help="Target path")
my_parser.add_argument("--flag", action="store_true", help="Optional flag")

# Add handler
def _cmd_mycommand(args) -> int:
    # Implementation
    return 0

# Wire in main()
if args.command == "mycommand":
    return _cmd_mycommand(args)
```

### 11.2 Add a New UI Dialog

1. Create dialog class in `ui/dialogs.py`
2. Use Qt Designer (optional) or code-based layout
3. Wire in `ui/main_window.py`

### 11.3 Add a New Agent Tool

In `agent/tools.py`:

```python
@tool
def my_new_tool(arg1: str, arg2: int = 10) -> str:
    """Description shown to the LLM.

    Args:
        arg1: Description of first argument.
        arg2: Description of second argument.

    Returns:
        Description of return value.
    """
    # Implementation
    return "result"
```

Then register in `agent/executor.py`:

```python
from . import tools

self.registry.register(tools.my_new_tool)
```

---

## 12. Environment Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `MBFORGE_LLM_PROVIDER` | LLM provider | `openai_compatible` |
| `MBFORGE_LLM_BASE_URL` | LLM API base URL | `http://localhost:8000/v1` |
| `MBFORGE_LLM_API_KEY` | LLM API key | `""` |
| `MBFORGE_LLM_MODEL` | Model name | `default` |
| `MBFORGE_LLM_MAX_TOKENS` | Max tokens | `4096` |
| `MBFORGE_LLM_TEMPERATURE` | Temperature | `0.7` |
| `MBFORGE_EMBED_PROVIDER` | Embedding provider | `sentence_transformers` |
| `MBFORGE_EMBED_MODEL` | Embedding model | `BAAI/bge-small-zh-v1.5` |
| `MBFORGE_EMBED_DEVICE` | Embedding device | `cpu` |
| `MBFORGE_RERANK_MODEL` | Rerank model | `BAAI/bge-reranker-base` |
| `MBFORGE_RERANK_DEVICE` | Rerank device | `cpu` |
| `MBFORGE_LOG_LEVEL` | Logging level | `INFO` |
| `MBFORGE_OPEN_PROJECT` | Pre-open project path | - |
| `UNIPARSER_HOST` | UniParser API host | - |
| `UNIPARSER_API_KEY` | UniParser API key | - |
