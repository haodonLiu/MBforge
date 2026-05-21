# MBForge Technology Stack

> 本文档详细列出 MBForge 所有使用的技术、库、工具及其版本和选型理由。

**Related Documentation:** [Architecture](ARCHITECTURE.md) · [API Reference](API.md) · [Development Guide](DEVELOPMENT.md) · [References](../REFERENCES.md)

---

## Overview

| Category | Technology | Version | Purpose |
|----------|-----------|---------|---------|
| **Language** | Python | >= 3.11 | Primary language |
| **UI Framework** | PyQt6 | >= 6.6 | Desktop GUI |
| **Vector DB** | ChromaDB | >= 0.4 | Semantic search |
| **Cheminformatics** | RDKit | >= 2024.3 | Molecule processing |
| **PDF Processing** | PyMuPDF | >= 1.25 | PDF text/image extraction |
| **Deep Learning** | PyTorch | >= 2.6 | Local model inference |
| **Embedding** | sentence-transformers | >= 2.5 | Text vectorization |
| **LLM Clients** | openai, anthropic | latest | API clients |
| **Package Manager** | uv | latest | Dependency management |
| **Testing** | pytest | >= 7.0 | Test framework |

---

## 1. Core Dependencies

### 1.1 Python >= 3.11

**Why:** Required for modern Python features (pattern matching, dataclass transforms, `type` introspection improvements). MBForge uses `from __future__ import annotations` throughout for forward references.

---

### 1.2 PyQt6 >= 6.6

```python
# UI
pyqt6>=6.6.0
pyqt6-webengine>=6.6.0
```

**Why PyQt6 over other frameworks?**

| Option | Pros | Cons |
|--------|------|------|
| **PyQt6** | Mature, full-featured Qt bindings; excellent documentation; cross-platform | GPL/commercial license |
| PySide6 | LGPL license, Qt Company official | Slightly less mature |
| tkinter | Built-in, no dependencies | Primitive UI |
| wxPython | Cross-platform | Less modern |

PyQt6 chosen for professional-grade UI capabilities (rich text, web view, tree widgets) and proven stability in scientific applications.

**QWebEngineView usage:** Markdown/HTML preview rendered via embedded Chromium (via `pyqt6-webengine`). Fallback to plain text if unavailable.

---

### 1.3 ChromaDB >= 0.4

```python
chromadb>=0.4.0
```

**Why ChromaDB?**

- Pure Python, no external server required (PersistentClient mode)
- cosine similarity by default (ideal for semantic search)
- Metadata filtering support
- Active development, OpenAI embedded embedding compatibility
- Anonymous telemetry disabled (`Settings(anonymized_telemetry=False)`)

**Usage pattern in MBForge:**
```python
client = chromadb.PersistentClient(path="./.mbforge/chroma_db")
collection = client.get_or_create_collection(
    name="docs",
    metadata={"hnsw:space": "cosine"},
)
```

---

### 1.4 RDKit >= 2024.3

```python
rdkit>=2024.3.0
```

**Why RDKit?**

- Gold standard open-source cheminformatics library
- SMILES/Mol/SDF parsing
- Descriptor calculation (MW, LogP, TPSA, HBD, HBA, etc.)
- Substructure searching
- Molecule drawing

**Used for:**
- `MoleculeRecord.mol` property (SMILES → RDKit Mol)
- `MoleculeRecord.compute_properties()` (auto-calculate descriptors)
- `MolRenderer` (molecule image generation)
- Molecule database property storage

---

### 1.5 PyMuPDF (fitz) >= 1.25

```python
pymupdf>=1.25.0
```

**Why PyMuPDF?**

- Fast PDF text extraction
- Image extraction from PDF pages
- Annotations and links support
- Lightweight (no external dependencies)
- Well-maintained fork of PyMuPDF (previously PyMuPDF)

**Used for:**
- `DocumentProcessor.process()` — PDF text extraction
- `DocumentProcessor.extract_pdf_images()` — pull images from PDF
- PDF page rendering (thumbnail generation)

---

### 1.6 sentence-transformers >= 2.5

```python
sentence-transformers>=2.5.0
```

**Why sentence-transformers?**

- Pre-trained models for sentence embeddings
- `BAAI/bge-small-zh-v1.5` for Chinese text (default embedder)
- `BAAI/bge-reranker-base` for cross-encoder reranking
- CPU-friendly models available
- Easy model swapping via model name

**Default models:**
| Model | Dim | Language | Use case |
|-------|-----|----------|----------|
| `BAAI/bge-small-zh-v1.5` | 512 | Chinese (+English) | Default embedding |
| `BAAI/bge-reranker-base` | 768 | Multilingual | Reranking |

---

### 1.7 PyTorch >= 2.6

```python
torch>=2.6.0
```

**Why PyTorch (CUDA 12.8)?**

- Required for sentence-transformers local inference
- CUDA 12.8 wheel for modern NVIDIA GPU support
- Used in `SentenceTransformerEmbedder` and `SentenceTransformerReranker`

**Note:** PyTorch (plus torchvision, torchaudio) is installed from custom index (`https://download.pytorch.org/whl/cu128`) via uv, not from default PyPI. torchvision and torchaudio are uv index sources only, not declared as package dependencies.

---

## 2. AI Model Clients

### 2.1 openai >= 1.0

```python
openai>=1.0.0
```

**Purpose:** Unified client for OpenAI-compatible APIs (vLLM, Ollama, SiliconFlow, etc.)

`OpenAILLM` uses `openai.OpenAI` with `base_url` override to support any OpenAI-compatible endpoint.

### 2.2 anthropic >= 0.103.1

```python
anthropic>=0.103.1
```

**Purpose:** Anthropic Claude series support via `AnthropicLLM`.

Used for Claude function calling (tool use) via `call_with_tools()` method.

---

## 3. Data & Storage

### 3.1 SQLite (built-in)

```python
# stdlib
import sqlite3
```

**Purpose:** `MoleculeDatabase` backing store.

**Schema features:**
- FTS5 virtual table for full-text search on molecule names/notes
- Indexes on `smiles`, `source_doc`, `activity`
- JSON columns for `properties` and `tags`

### 3.2 lxml >= 6.0

```python
lxml>=6.0.0
```

**Purpose:** XML/HTML processing (PDF extracted content, HTML preview).

---

## 4. Scientific Computing

### 4.1 numpy >= 1.26.4, < 2.0

```python
numpy>=1.26.4,<2.0.0
```

**Purpose:** Array operations, numerical computing throughout.

**Version constraint:** Upper bound prevents breaking changes from numpy 2.x.

### 4.2 pandas >= 2.3.3, < 3.0

```python
pandas>=2.3.3,<3.0.0
```

**Purpose:** Tabular data handling (CSV export from molecule database, etc.).

### 4.3 scipy >= 1.13

```python
scipy>=1.13.0
```

**Purpose:** Scientific algorithms (used in QSAR workflow stubs).

---

## 5. Visualization

### 5.1 matplotlib >= 3.7

```python
matplotlib>=3.7.0
```

**Purpose:** Molecule 2D rendering, chart generation.

### 5.2 seaborn >= 0.12

```python
seaborn>=0.12.0
```

**Purpose:** Statistical visualization (SAR analysis plots in openSAR).

### 5.3 networkx >= 3.0

```python
networkx>=3.0
```

**Purpose:** Graph algorithms (molecule structure graphs, workflow dependency graphs).

### 5.4 Pillow >= 10.4

```python
pillow>=10.4.0
```

**Purpose:** Image processing (PDF thumbnails, molecule image export).

### 5.5 opencv-python >= 4.10

```python
opencv-python>=4.10.0
```

**Purpose:** Image preprocessing for VLM analysis (image normalization, cropping).

---

## 6. Document Processing

### 6.1 latex2mathml >= 3.77

```python
latex2mathml>=3.77.0
```

**Purpose:** Convert LaTeX equations to MathML for HTML preview.

### 6.2 pylatexenc >= 2.10

```python
pylatexenc>=2.10
```

**Purpose:** LaTeX encoding/decoding (parsing LaTeX in PDF content).

### 6.3 markdown >= 3.6

```python
markdown>=3.6
```

**Purpose:** Markdown → HTML conversion for preview pane.

### 6.4 html5lib >= 1.1

```python
html5lib>=1.1
```

**Purpose:** HTML parsing for markdown output validation.

---

## 7. Configuration & Environment

### 7.1 python-dotenv >= 1.0

```python
python-dotenv>=1.0.0
```

**Purpose:** Load `.env` file for environment variable management.

### 7.2 pydantic >= 2.0

```python
pydantic>=2.0.0
```

**Purpose:** Data validation for config dataclasses.

### 7.3 platformdirs >= 4.0

```python
platformdirs>=4.0.0
```

**Purpose:** Cross-platform config directory resolution (`~/.config/MBForge/`).

### 7.4 pyyaml >= 6.0

```python
pyyaml>=6.0.0
```

**Purpose:** YAML parsing for configuration files.

---

## 8. Networking

### 8.1 requests >= 2.32

```python
requests>=2.32.0
```

**Purpose:** HTTP requests for UniParser API calls.

### 8.2 aiohttp >= 3.9

```python
aiohttp>=3.9.0
```

**Purpose:** Async HTTP for concurrent API calls.

---

## 9. Package Management

### 9.1 uv

```bash
# Installed separately, not a pip dependency
pip install uv
```

**Why uv?**

- 10-100x faster than pip
- Native workspace support (manages `setup/openSAR` and `setup/UniParser-Tools` as members)
- `pyproject.toml` based
- Lock file generation

**Workspace members:**
```toml
[tool.uv.workspace]
members = ["setup/UniParser-Tools", "setup/openSAR"]
```

**Custom index for PyTorch:**
```toml
[[tool.uv.index]]
name = "pytorch-cu128"
url = "https://download.pytorch.org/whl/cu128"
explicit = true
```

**Tsinghua mirror:**
```toml
[tool.uv]
index-url = "https://pypi.tuna.tsinghua.edu.cn/simple"
```

---

## 10. Development Tools

### 10.1 pytest >= 7.0

```python
dev = ["pytest>=7.0.0", "pytest-cov>=4.0.0", ...]
```

**Purpose:** Unit and integration testing.

**Configuration (`pyproject.toml`):**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--import-mode=importlib"
pythonpath = ["src"]
```

### 10.2 ruff >= 0.1.0

```python
dev = ["ruff>=0.1.0"]
```

**Purpose:** Fast linting (replaces flake8, isort, black).

### 10.3 mypy >= 1.0

```python
dev = ["mypy>=1.0.0"]
```

**Purpose:** Static type checking.

### 10.4 pyinstaller >= 6.0

```python
dev = ["pyinstaller>=6.0.0"]
```

**Purpose:** EXE packaging for Windows distribution.

---

## 11. Local Components

### 11.1 openSAR (in `setup/openSAR/`)

Installed as `csar` package via uv workspace.

**Purpose:** SAR (Structure-Activity Relationship) analysis toolkit. Not yet integrated into MBForge core.

**Contents:** Statistical analysis, visualization tools for SAR data.

### 11.2 UniParser-Tools (in `setup/UniParser-Tools/`)

Installed as `uniparser-tools` package via uv workspace.

**Purpose:** Remote PDF parsing API (OCR, table extraction, molecule recognition). Currently wrapped by `ParserClient` but not used in core pipeline (PyMuPDF is used instead).

**API:** REST-based, requires `UNIPARSER_HOST` and `UNIPARSER_API_KEY`.

---

## 12. Dependency Graph

```
mbforge (main)
├── core/
│   ├── project.py         → json, pathlib
│   ├── knowledge_base.py  → chromadb
│   ├── mol_database.py    → sqlite3, rdkit, json
│   ├── document.py        → pymupdf (fitz), PIL
│   └── summarizer.py      → llm (BaseLLM)
├── models/
│   ├── llm.py             → openai
│   ├── anthropic_llm.py   → anthropic
│   ├── embedding.py       → sentence_transformers, torch
│   └── rerank.py          → sentence_transformers, torch
├── parsers/
│   ├── pdf_parser.py      → pymupdf, tempfile, llm, vlm, kb, mol_db
│   └── molecule_extractor.py → rdkit, re, llm
├── agent/
│   ├── agent.py           → llm, context, executor, memory_manager
│   └── tools.py           → kb, mol_db, document_processor
└── ui/
    ├── main_window.py     → PyQt6
    └── ...
```

---

## 13. Version Constraints

### numpy / pandas upper bounds

```toml
override-dependencies = [
    "pandas>=2.3.3,<3.0.0",
    "numpy>=1.26.4,<2.0.0",
]
```

**Why:** Prevent accidental numpy 2.x / pandas 3.x breaking changes from propagating into the environment.

### PyTorch from CUDA 12.8 index

```toml
[tool.uv.sources]
torch = { index = "pytorch-cu128" }
```

**Why:** Ensure GPU acceleration is available for sentence-transformers on modern NVIDIA hardware.
