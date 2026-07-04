# References & Acknowledgments

> Last updated: 2026-06-29, after the Rust→Python migration.
> MBForge builds on the work of many open-source projects and services.
> Thank you to the teams behind each.

---

## Core Frameworks

| Project | License | Used for |
|---|---|---|
| [FastAPI](https://fastapi.tiangolo.com/) | MIT | Python backend (REST + SSE) |
| [LangGraph](https://langchain-ai.github.io/langgraph/) | MIT | Agent orchestration graph |
| [LangChain](https://www.langchain.com/) | MIT | LLM provider abstraction |
| [React](https://react.dev/) | MIT | Frontend UI framework |
| [Vite](https://vitejs.dev/) | MIT | Frontend build tool |
| [Pydantic](https://docs.pydantic.dev/) | MIT | Request/response validation |

## PDF Parsing

| Project | License | Used for |
|---|---|---|
| [pdfplumber](https://github.com/jsvine/pdfplumber) | MIT | Text + layout extraction |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | Apache-2.0 | Page rendering (image fallback) |
| [MinerU](https://mineru.net/) | Commercial API | Cloud OCR for difficult PDFs |
| [UniParser](https://uniparser.dp.tech/) | Commercial API | Cloud document parsing |
| [LlamaIndex LlamaParse](https://www.llamaindex.ai/) | Commercial API | Cloud parsing fallback |

> **Removed**: pdf-inspector, lopdf, PyMuPDF (replaced by pdfplumber + pypdfium2).

## Cheminformatics

| Project | License | Used for |
|---|---|---|
| [RDKit](https://www.rdkit.org/) | BSD-3-Clause | Fingerprints, descriptors, SMILES parsing |
| [MolScribe](https://github.com/thomas0809/MolScribe) | MIT | Molecule image → SMILES recognition |
| [OpenBabel](https://openbabel.org/) | GPL-2.0 | Format conversion (optional) |
| [E-SMILES](https://github.com/thomas0809/MolScribe) | — | Extended SMILES spec |

### MolScribe Sub-dependencies

| Component | License | Source |
|---|---|---|
| Swin Transformer | MIT | [Microsoft Swin Transformer](https://github.com/microsoft/Swin-Transformer) |
| OpenNMT-py Decoder | MIT | [OpenNMT](https://opennmt.net/) |

## AI Models

| Model | License | Source |
|---|---|---|
| Qwen3-Embedding-0.6B | Apache-2.0 | [Qwen (Alibaba)](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) |
| Qwen3-Reranker-0.6B | Apache-2.0 | [Qwen (Alibaba)](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B) |
| MolDetv2 (YOLO26n) | Apache-2.0 | [yujieq/MolDetect](https://huggingface.co/yujieq/MolDetect) |
| MolScribe | MIT | [yujieq/MolScribe](https://huggingface.co/yujieq/MolScribe) |

## Storage & Retrieval

| Project | License | Used for |
|---|---|---|
| [OpenKB](https://github.com/your-org/openkb) + [PageIndex](https://github.com/VectifyAI/PageIndex) | MIT | Vectorless tree reasoning + dense rerank (per-project KB index) |
| [SQLite](https://www.sqlite.org/) | Public Domain | Business data persistence |
| [sentence-transformers](https://www.sbert.net/) | Apache-2.0 | Embedding model framework |
| [HuggingFace Transformers](https://huggingface.co/docs/transformers) | Apache-2.0 | Model loading & inference |

> **Removed**: ChromaDB, rusqlite (→ OpenKB / PageIndex), Zvec (→ OpenKB / PageIndex via commit `4fbde55`).

## ML Inference

| Project | License | Used for |
|---|---|---|
| [PyTorch](https://pytorch.org/) | BSD-3-Clause | ML backend (CUDA 12.8 optional) |
| [Ultralytics (YOLO)](https://ultralytics.com/) | AGPL-3.0 | MolDetv2 object detection |

## Design Inspirations

| Project | Reference |
|---|---|
| [OpenViking](https://github.com/volcengine/OpenViking) | Knowledge base architecture |
| [TencentDB-Agent-Memory](https://github.com/Tencent/TencentDB-Agent-Memory) | Agent memory system design |
| [RxnScribe](https://github.com/thomas0809/RxnScribe) | Reaction diagram parsing |
| [OpenChemIE](https://github.com/CrystalEye42/OpenChemIE) | Chemical information extraction |

## LLM Extraction Methodology

| Work | Use |
|---|---|
| [Dagdelen et al. 2024 (Nature Comm. 15:1418)](https://doi.org/10.1038/s41467-024-45563-x) | LLM-NERRE: joint NER + relation extraction. Our post-process prompt borrows the JSON schema and the "canonicalization is extraction" principle. |

## Academic Papers

| Paper | Use |
|---|---|
| "MolParser: End-to-end Visual Recognition of Molecule Structures in the Wild" (arXiv:2411.11098) | E-SMILES format origin |
| Qwen3 technical report | Embedding/reranker architecture reference |
| MolScribe (Nat. Mach. Intell. 2023) | Molecule OCR architecture reference |

---

*If you maintain one of the projects above and would like to be acknowledged
differently, or if any attribution is incorrect, please open an issue.*