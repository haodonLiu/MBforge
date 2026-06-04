# MBForge Tech Stack

> 所有依赖的技术选型、版本要求和使用场景。

**Related:** [Architecture](ARCHITECTURE.md) · [References](../REFERENCES.md)

---

## Overview

| Category | Technology | Version | Purpose |
|----------|-----------|---------|---------|
| **Frontend** | React + Vite + TypeScript | 19 / 6 / 5.7 | Browser UI |
| **Desktop Shell** | Tauri | v2 | Native desktop wrapper |
| **Backend** | FastAPI + uvicorn | >= 0.115 / >= 0.34 | REST API server |
| **Vector DB** | SQLite FTS5 + semantic_cache (Rust) | — | Semantic search |
| **Cheminformatics** | RDKit | >= 2024.3 | Molecule processing |
| **PDF Processing** | PyMuPDF | >= 1.25 | PDF text/image extraction |
| **Deep Learning** | PyTorch | >= 2.6 (CUDA 12.8) | Local model inference |
| **Embedding** | sentence-transformers | >= 2.5 | Text vectorization |
| **LLM Clients** | openai, anthropic | latest | API clients |
| **Package Manager** | uv | latest | Dependency management |
| **Testing** | pytest | >= 7.0 | Test framework |

---

## 1. Frontend

### React 19 + Vite 6 + TypeScript 5.7

```json
{
  "react": "^19.0.0",
  "vite": "^6.0.0",
  "typescript": "^5.7.0"
}
```

**Why:** Modern React with fast HMR via Vite. TypeScript for type safety. Tauri wraps the web frontend into a native desktop app.

### Tauri v2

```toml
[dependencies]
tauri = { version = "2", features = ["shell"] }
```

**Why:** Lightweight native shell (~10MB vs Electron's ~150MB). Rust backend for system access. Spawns Python model server as child process.

---

## 2. Backend

### FastAPI + uvicorn

```toml
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
```

**Why:** Async Python web framework with automatic OpenAPI docs. Used for the model server that handles AI inference requests.

### Pydantic

```toml
pydantic>=2.0.0
```

**Why:** Data validation for API request/response models. Used throughout for configuration and data classes.

---

## 3. AI / ML

### PyTorch (CUDA 12.8)

```toml
torch>=2.6.0
torchvision>=0.21.0
torchaudio>=0.21.0
```

**Why:** Backend for sentence-transformers and ultralytics. CUDA 12.8 for GPU acceleration.

### sentence-transformers

```toml
sentence-transformers>=2.5.0
```

**Why:** Local embedding (Qwen3-Embedding) and reranking (BGE-reranker). No API costs for local inference.

### SQLite FTS5 + semantic_cache

Rust 侧使用 SQLite FTS5 全文搜索 + `semantic_cache.json` 查询缓存。有 Embedder 时叠加向量余弦相似度 + RRF 融合排序。

---

## 4. Chemistry

### RDKit

```toml
rdkit>=2024.3.0
```

**Why:** Industry-standard cheminformatics library. Molecular fingerprints, descriptors, substructure search, SMILES parsing.

### PyMuPDF

```toml
pymupdf>=1.25.0
```

**Why:** Fast PDF text and image extraction. Core of the document processing pipeline.

### OpenBabel

```toml
openbabel-wheel>=3.1.1
```

**Why:** Molecular file format conversion (SDF, MOL, MOL2, PDB, etc.).

---

## 5. Image Processing

### ultralytics

```toml
ultralytics>=8.3.0
```

**Why:** YOLO-based molecule detection in PDF images. Detects and extracts molecular structures from figures.

### Pillow + opencv-python

```toml
pillow>=10.4.0
opencv-python>=4.10.0
```

**Why:** Image manipulation for PDF rendering and molecule detection preprocessing.

---

## 6. Development Tools

### uv

**Why:** Fast Python package manager (10-100x faster than pip). Workspace support for monorepo structure.

### ruff

```toml
ruff>=0.1.0
```

**Why:** Fast Python linter and formatter (written in Rust). Replaces flake8 + black + isort.

### pytest

```toml
pytest>=7.0.0
```

**Why:** Standard Python testing framework. Used with pytest-cov for coverage.
