# MBForge Development Guide

> 开发环境配置、代码规范、调试方法和贡献指南。

**Related:** [Architecture](ARCHITECTURE.md) · [API Reference](API.md) · [Tech Stack](TECH_STACK.md)

---

## 1. Environment Setup

### Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend)
- [uv](https://github.com/astral-sh/uv) package manager
- Git

### Clone & Install

```bash
git clone https://github.com/haodonLiu/MBforge.git
cd MBForge

# Backend
uv sync --dev

# Frontend
cd frontend && npm install

# Environment
cp .env.template .env
# Edit .env with API keys
```

---

## 2. Running

### Model Server (Backend)

```bash
uv run uvicorn mbforge.model_server.main:app --host 127.0.0.1 --port 18792
```

### Frontend Dev Server

```bash
cd frontend && npm run dev
# Opens http://localhost:5173
```

### Full Application (Tauri)

```bash
cd src-tauri && cargo tauri dev
```

### CLI

```bash
# Initialize project
mbforge init ./my-project --name "MyProject"

# Index PDFs
mbforge index ./my-project

# Start GUI (model server + browser)
mbforge gui
```

---

## 3. Testing

```bash
# All tests
uv run pytest tests/ -v

# Specific file
uv run pytest tests/unit/test_project.py -v

# With coverage
uv run pytest tests/ --cov=mbforge --cov-report=html
```

---

## 4. Code Quality

```bash
# Format
uv run ruff format src/

# Lint
uv run ruff check src/

# Type check
uv run mypy src/

# Frontend build check
cd frontend && npm run build
```

---

## 5. Project Structure

```
core/       → Data models (Project, KnowledgeBase, MoleculeDatabase)
models/     → AI model abstraction (LLM, Embedder, Reranker, VLM)
parsers/    → PDF parsing and molecule extraction
agent/      → ReAct agent with tool execution
model_server/ → FastAPI routers and model singletons
workflow/   → Extension modules (stubs)
utils/      → Config, logging, helpers
frontend/   → React+Vite frontend
src-tauri/  → Tauri desktop shell
rust/       → Optional Rust acceleration (PyO3)
```

---

## 6. Adding a New API Endpoint

1. Create router in `src/mbforge/model_server/routers/`
2. Add dependency injection in `dependencies.py` if needed
3. Register in `main.py` via `app.include_router()`

```python
# routers/my_router.py
from fastapi import APIRouter, Depends
from ..dependencies import get_project_from_root

router = APIRouter()

@router.get("/my-endpoint")
async def my_endpoint(project: Project = Depends(get_project_from_root)):
    return {"success": True}
```

---

## 7. Adding a New Agent Tool

1. Define tool in `src/mbforge/agent/tools.py`
2. Register in `ToolExecutor.registry`
3. Export via `registry.to_openai_schemas()`

---

## 8. Logging

```python
from mbforge.utils.logger import get_logger

logger = get_logger(__name__)
logger.info("Operation completed")
logger.error("Failed: %s", error)
```

---

## 9. Package Management

```bash
# Add dependency
uv add some-package

# Add dev dependency
uv add --dev some-package

# Update lock file
uv lock
```

---

## 10. Build & Release

### Desktop App (Tauri)

```bash
cd src-tauri && cargo tauri build
# Output: src-tauri/target/release/bundle/
```

### Version Bump

Update version in `pyproject.toml`:
```toml
[project]
version = "0.2.0"
```
