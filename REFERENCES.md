# MBForge References

> 本文件列出 MBForge 项目使用的所有开源库、工具和服务，并附上相应的引用信息。

**Related Documentation:** [Architecture](docs/ARCHITECTURE.md) · [API Reference](docs/API.md) · [Development Guide](docs/DEVELOPMENT.md) · [Tech Stack](docs/TECH_STACK.md)

---

## Table of Contents

- [Programming Language](#1-programming-language)
- [UI Framework](#2-ui-framework)
- [Vector Database](#3-vector-database)
- [Cheminformatics](#4-cheminformatics)
- [PDF Processing](#5-pdf-processing)
- [Deep Learning & Embedding](#6-deep-learning--embedding)
- [LLM Clients](#7-llm-clients)
- [Data Processing](#8-data-processing)
- [Scientific Computing](#9-scientific-computing)
- [Visualization](#10-visualization)
- [Document Rendering](#11-document-rendering)
- [Configuration & Environment](#12-configuration--environment)
- [Networking](#13-networking)
- [Package Management](#14-package-management)
- [Development Tools](#15-development-tools)
- [Local Components](#16-local-components)
- [Design Influences](#17-design-influences)

---

## 1. Programming Language

### Python

> Van Rossum, G. & Drake, F.L. (2009). *Python 3 Reference Manual*. Scotts Valley, CA: CreateSpace.

- Website: https://www.python.org/
- Version: >= 3.11

---

## 2. UI Framework

### PyQt6

> Riverbank Computing Ltd. (2024). *PyQt6 Documentation*. https://doc.qt.org/

- Website: https://www.riverbankcomputing.com/software/pyqt/
- Version: >= 6.6
- License: GPL v3 / Commercial

### Qt / QWebEngineView

> The Qt Company. (2024). *Qt Documentation*. https://doc.qt.org/

- Website: https://www.qt.io/
- Used for: Markdown/HTML preview rendering via embedded Chromium

---

## 3. Vector Database

### ChromaDB

> ChromaDB Authors. (2024). *Chroma - the AI-native open-source embedding database*.

- GitHub: https://github.com/chroma-core/chroma
- Website: https://www.trychroma.com/
- Version: >= 0.4
- License: Apache 2.0

---

## 4. Cheminformatics

### RDKit

> Landrum, G. (2024). *RDKit Documentation*. https://www.rdkit.org/

- GitHub: https://github.com/rdkit/rdkit
- Website: https://www.rdkit.org/
- Version: >= 2024.3
- License: BSD-3-Clause

**Citation:**
> Landrum, G. et al. (2024). RDKit: A toolkit for cheminformatics. https://doi.org/10.5281/zenodo.591687

---

## 5. PDF Processing

### PyMuPDF (fitz)

> Artifex Software Inc. (2024). *PyMuPDF Documentation*.

- GitHub: https://github.com/pymupdf/PyMuPDF
- Website: https://pymupdf.readthedocs.io/
- Version: >= 1.25
- License: AGPL v3 / Commercial

---

## 6. Deep Learning & Embedding

### PyTorch

> Paszke, A., Gross, S., Massa, F., Lerer, A., et al. (2019). *PyTorch: An Imperative Style, High-Performance Deep Learning Library*. In Advances in Neural Information Processing Systems 32 (NeurIPS 2019).

- GitHub: https://github.com/pytorch/pytorch
- Website: https://pytorch.org/
- Version: >= 2.6
- License: BSD-3-Clause

**Citation:**
> Paszke, A., Gross, S., Massa, F., Lerer, A., et al. (2019). PyTorch: An Imperative Style, High-Performance Deep Learning Library. *NeurIPS 2019*. https://arxiv.org/abs/1912.01703

### sentence-transformers

> Reimers, N. & Gurevych, I. (2019). *Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks*. In Proceedings of EMNLP-IJCNLP 2019.

- GitHub: https://github.com/UKPLab/sentence-transformers
- Website: https://www.sbert.net/
- Version: >= 2.5
- License: Apache 2.0

**Citation:**
> Reimers, N. & Gurevych, I. (2019). Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks. *EMNLP-IJCNLP 2019*. https://arxiv.org/abs/1908.10084

### BGE (Beijing General Embedding) Models

> FlagAI Team. (2024). *BAAI/bge-small-zh-v1.5*.

- HuggingFace: https://huggingface.co/BAAI/bge-small-zh-v1.5
- Model Description: State-of-the-art Chinese embedding model, 512 dimensions, 0.4B parameters

**Citation for BGE-reranker-base:**
> FlagAI Team. (2024). *BAAI/bge-reranker-base*. BAAI.

- HuggingFace: https://huggingface.co/BAAI/bge-reranker-base
- Model Description: Cross-encoder reranking model for improved semantic search results

---

## 7. LLM Clients

### OpenAI Python SDK

> OpenAI. (2024). *OpenAI Python API Documentation*.

- GitHub: https://github.com/openai/openai-python
- Website: https://platform.openai.com/
- Version: >= 1.0
- License: Apache 2.0

### Anthropic Python SDK

> Anthropic. (2024). *Anthropic Python SDK*.

- GitHub: https://github.com/anthropics/anthropic-sdk-python
- Website: https://www.anthropic.com/
- Version: >= 0.103.1
- License: Apache 2.0

---

## 8. Data Processing

### pandas

> McKinney, W. (2010). *Data Structures for Statistical Computing in Python*. In Proceedings of the 9th Python in Science Conference (SciPy 2010).

- Website: https://pandas.pydata.org/
- Version: >= 2.3.3, < 3.0
- License: BSD-3-Clause

**Citation:**
> McKinney, W. (2010). Data Structures for Statistical Computing in Python. *SciPy 2010*. https://doi.org/10.25080/Majora-92bf3192-00a

### numpy

> Harris, C.R., Millman, K.J., van der Walt, S.J., et al. (2020). *Array programming with NumPy*. Nature 585, 357–362.

- Website: https://numpy.org/
- Version: >= 1.26.4, < 2.0
- License: BSD-3-Clause

**Citation:**
> Harris, C.R., Millman, K.J., van der Walt, S.J., et al. (2020). Array programming with NumPy. *Nature* 585, 357–362. https://doi.org/10.1038/s41586-020-2649-2

---

## 9. Scientific Computing

### SciPy

> Virtanen, P., Gommers, R., Oliphant, T.E., et al. (2020). *SciPy 1.0: Fundamental Algorithms for Scientific Computing in Python*. Nature Methods 17, 261–272.

- Website: https://scipy.org/
- Version: >= 1.13
- License: BSD-3-Clause

**Citation:**
> Virtanen, P., Gommers, R., Oliphant, T.E., et al. (2020). SciPy 1.0: Fundamental Algorithms for Scientific Computing in Python. *Nature Methods* 17, 261–272. https://doi.org/10.1038/s41592-019-0686-2

---

## 10. Visualization

### matplotlib

> Hunter, J.D. (2007). *Matplotlib: A 2D Graphics Environment*. Computing in Science & Engineering, 9(3), 90-95.

- Website: https://matplotlib.org/
- Version: >= 3.7
- License: PSF

**Citation:**
> Hunter, J.D. (2007). Matplotlib: A 2D Graphics Environment. *Computing in Science & Engineering*, 9(3), 90-95. https://doi.org/10.1109/MCSE.2007.55

### seaborn

> Waskom, M.L. (2021). *seaborn: statistical data visualization*. Journal of Open Source Software, 6(60), 3021.

- Website: https://seaborn.pydata.org/
- Version: >= 0.12
- License: BSD-3-Clause

**Citation:**
> Waskom, M.L. (2021). seaborn: statistical data visualization. *Journal of Open Source Software*, 6(60), 3021. https://doi.org/10.21105/joss.03021

### Pillow

> Clark, A. & Contributors. (2024). *Pillow: Python Imaging Library*.

- GitHub: https://github.com/python-pillow/Pillow
- Website: https://pillow.readthedocs.io/
- Version: >= 10.4
- License: HPND

### opencv-python

> Bradski, G. (2000). *The OpenCV Library*. Dr. Dobb's Journal of Software Tools.

- Website: https://opencv.org/
- Version: >= 4.10
- License: Apache 2.0

---

## 11. Document Rendering

### markdown

> Gruber, J. & Contributors. (2024). *Python Markdown*.

- GitHub: https://github.com/Python-Markdown/markdown
- Website: https://python-markdown.github.io/
- Version: >= 3.6
- License: BSD-3-Clause

### latex2mathml

> Kinner, R. (2024). *latex2mathml: Convert LaTeX to MathML*.

- GitHub: https://github.com/ronieto/latex2mathml
- Version: >= 3.77
- License: MIT

### pylatexenc

> Frelat, J. & Contributors. (2024). *pylatexenc: LaTeX encoder/decoder*.

- GitHub: https://github.com/phfaist/pylatexenc
- Version: >= 2.10
- License: GPL v2 / Commercial

### html5lib

> html5lib Contributors. (2024). *html5lib: Pure Python library for parsing HTML*.

- GitHub: https://github.com/html5lib/html5lib-python
- Website: https://html5lib.readthedocs.io/
- Version: >= 1.1
- License: MIT

---

## 12. Configuration & Environment

### python-dotenv

> Saurabh Kumar. (2024). *python-dotenv: Read key-value pairs from .env file*.

- GitHub: https://github.com/theskumar/python-dotenv
- Website: https://saurabh-kumar.com/python-dotenv/
- Version: >= 1.0
- License: BSD-3-Clause

### pydantic

> Colvin, S. & Contributors. (2024). *Pydantic: Data validation using Python type annotations*.

- GitHub: https://github.com/pydantic/pydantic
- Website: https://docs.pydantic.dev/
- Version: >= 2.0
- License: MIT

### platformdirs

> Ofek, G. & Contributors. (2024). *platformdirs: Cross-platform standard library*.

- GitHub: https://github.com/platformdirs/platformdirs
- Website: https://platformdirs.readthedocs.io/
- Version: >= 4.0
- License: MIT

### PyYAML

> Simyon. (2024). *PyYAML: YAML parser and emitter for Python*.

- GitHub: https://github.com/yaml/pyyaml
- Website: https://pyyaml.org/
- Version: >= 6.0
- License: MIT

---

## 13. Networking

### requests

> Reitz, K. & Collaborators. (2024). *Requests: HTTP for Humans*.

- GitHub: https://github.com/psf/requests
- Website: https://requests.readthedocs.io/
- Version: >= 2.32
- License: Apache 2.0

### aiohttp

> Kulkarni, M. & Contributors. (2024). *aiohttp: Asynchronous HTTP client/server for asyncio*.

- GitHub: https://github.com/aio-libs/aiohttp
- Website: https://docs.aiohttp.org/
- Version: >= 3.9
- License: Apache 2.0

---

## 14. Package Management

### uv

> Astral Software. (2024). *uv: An extremely fast Python package installer and resolver*.

- GitHub: https://github.com/astral-sh/uv
- Website: https://docs.astral.sh/uv/
- License: Apache 2.0 / MIT

---

## 15. Development Tools

### pytest

> Krekel, H. & Contributors. (2024). *pytest: simple powerful testing with Python*.

- GitHub: https://github.com/pytest-dev/pytest
- Website: https://pytest.org/
- Version: >= 7.0
- License: MIT

### ruff

> Astral Software. (2024). *ruff: An extremely fast Python linter and code formatter, written in Rust*.

- GitHub: https://github.com/astral-sh/ruff
- Website: https://docs.astral.sh/ruff/
- Version: >= 0.1.0
- License: MIT

### mypy

> Lehtosalo, M. & Contributors. (2024). *mypy: Static type checker for Python*.

- GitHub: https://github.com/python/mypy
- Website: https://mypy-lang.org/
- Version: >= 1.0
- License: MIT

### PyInstaller

> PyInstaller Development Team. (2024). *PyInstaller: Freeze Python programs into stand-alone executables*.

- GitHub: https://github.com/pyinstaller/pyinstaller
- Website: https://pyinstaller.org/
- Version: >= 6.0
- License: GPL v2 / Commercial

---

## 16. Local Components

### openSAR

> MBForge Team. (2024). *openSAR: SAR Analysis Toolkit*.

- Location: `setup/openSAR/`
- Package name: `csar`
- Status: Workspace member, not yet integrated into MBForge core

### UniParser-Tools

> UniParser Team. (2024). *UniParser-Tools: PDF Parsing and OCR Tools*.

- Location: `setup/UniParser-Tools/`
- Package name: `uniparser-tools`
- Status: Workspace member, wrapped by `mbforge.parsers.uniparser.ParserClient`

---

## 17. Design Influences

### Obsidian

> Obsidian.md. (2024). *Obsidian: A second brain, for you, forever*.

- Website: https://obsidian.md/
- Influence: Vault-based project management, folder = project

**Design Reference:** Vault metaphor and hidden metadata directory pattern.

### ChromaDB Architecture (TencentDB-Agent-Memory)

> ChromaDB Authors. (2024). Based on ChromaDB persistent client design for local vector storage with metadata filtering.

**Design Reference:** `KnowledgeBase` class architecture and hybrid search + rerank pattern.

### TencentDB-Agent-Memory

> Tencent. (2024). *TencentDB Agent Memory Architecture*.

- Reference: https://github.com/Tencent/TencentDB-Agent-Memory

**Design Reference:** 6-type memory system, layered context management, memory injection into system prompt.

### OpenViking

> Volcano Engine. (2024). *OpenViking: Knowledge Base Architecture*.

- Reference: https://github.com/volcengine/OpenViking

**Design Reference:** Recursive directory-level semantic search (`search_by_directory`).

### ReAct (Synergizing Reasoning and Acting)

> Yao, S., Zhao, J., Yu, D., et al. (2023). *ReAct: Synergizing Reasoning and Acting in Language Models*. ICLR 2023.

- Paper: https://arxiv.org/abs/2210.03629

**Design Reference:** ReAct loop in `ProjectAgent`, tool execution with thought process.

### OpenAI Function Calling

> OpenAI. (2023). *Function calling and instruction following for GPT-4*.

- Reference: https://platform.openai.com/docs/guides/function-calling

**Design Reference:** Tool schema definition and execution in `ToolExecutor.registry`.
