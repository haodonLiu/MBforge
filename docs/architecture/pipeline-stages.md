# MBForge Pipeline — Stage Reference

> **Last verified:** 2026-07-14  
> **Canonical model:** **7 logical stages** (`pipeline/stages/*.py` + `StageExecutor`)  
> **Entry point:** `mbforge.pipeline.runner.run_pipeline(pdf_path, library_root, …)`  
> If this file drifts from code, **the code wins**.

## At a glance

```
PDF
 → Extract      (text + OCR fallback)
 → Density      (text_only / mixed / image_only)
 → Markdown     (rough_md + MolDetv2-FT/MolScribe + MoleCode)
 → Reorganize   (LLM reorg + optional MinerU-Popo)
 → Activity     (IC50 / Ki / EC50 / Kd from tables)
 → Index        (PageIndex tree + Wiki)
 → Persist      (molecules + links + document, single txn intent)
```

Orchestrator: `pipeline/runner.py`  
Shared state: `pipeline/context.py:PipelineContext`  
Contract: `pipeline/stages/base.py:StageExecutor` → `StageResult`  
Progress map: `STAGE_PCT` in `runner.py` (extract 10 → … → persist 100).

Internal sub-steps (rough_md / detect / insert_molecode / popo / pageindex / wiki /
persist_mols / register_links) are **implementation details inside** the 7 stage
classes — not separate top-level stages. Older docs that list “9 stages” describe
those sub-steps, not the current `STAGES` registry.

---

## Stage table

| # | Stage class | Key helpers | Purpose | Primary outputs |
|---|---|---|---|---|
| 1 | `ExtractStage` | `extract_text.extract_pdf_text` | PyMuPDF native text + OCR chain for sparse pages | `ExtractedDocument` on context |
| 2 | `DensityStage` | `classify.classify_density` | `text_only` / `mixed` / `image_only` | density fields on context |
| 3 | `MarkdownStage` | `write_rough_markdown`, `extract_molecules_from_pdf`, `insert_molecode_blocks` | Rough MD + FT detect + MolScribe + MoleCode | enriched markdown path, molecule candidates |
| 4 | `ReorganizeStage` | `organizer.reorganize_with_llm`, optional `popo` | Semantic reorg; rule fallback if degenerate | `storage/{doc_id}/reorganized.md` |
| 5 | `ActivityStage` | `extract_activities` | Table activity values + molecule linking | activity rows / stats on context |
| 6 | `IndexStage` | OpenKB adapter `index_markdown` + wiki compile | PageIndex tree + wiki artifacts | `.mbforge/openkb/` |
| 7 | `PersistStage` | `persist_molecules`, link registration, doc report | Persist molecules + links + report/pages | SQLite + `storage/{doc_id}/` |

HTTP twin for detection path: `routers/moldet_api.py` (page extract).

---

## Per-stage notes

### 1 — Extract

- Native text via PyMuPDF; pages with very little text go to OCR.
- OCR chain (cloud-first): MinerU → PaddleOCR → GLMOCR → RapidOCR (`backends/ocr/chain.py`).
- Config: `AppConfig.ocr` via `load_global_config()` / settings UI — not a separate `configs/ocr.yaml` runtime file.

### 2 — Density

- Classifies document kind from OCR-need ratio + total text length.
- Downstream may short-circuit expensive LLM reorg for pure text-only with no molecules.

### 3 — Markdown (detect + MoleCode)

- Detector: **`backends/moldet_v2_ft.py`** (YOLO26n FT — joint molecule + coref labels).  
  `backends/moldet.py` is a compat shim only.
- Recognizer: MolScribe → SMILES; normalize/dedup via RDKit + element whitelist.
- Crops write under **`storage/{doc_id}/crops/`** via `ArtifactResolver` (legacy
  `.mbforge/crops/` remains read fallback until migration).
- MoleCode blocks inserted into markdown for later link registration.

### 4 — Reorganize

- LLM reorganize with chunking; optional Popo gated by settings.
- Degenerate output falls back to rule-based structure.

### 5 — Activity

- Extracts IC50 / Ki / EC50 / Kd style values from tables.
- Linking prefers name → SMILES → page-proximity fallback (see pipeline tests).

### 6 — Index

- PageIndex tree + wiki compilation through `openkb/` adapter.
- Failure should not erase already-extracted molecules (best-effort cascade).

### 7 — Persist

- Molecules, text–molecule links, report.json, per-page texts.
- DB target: **`{library_root}/.mbforge/library.db`** (unified). Legacy
  `index/knowledge_base.db` + `index/molecules.db` only as migration fallback.

---

## Final filesystem layout (canonical)

```
{library_root}/
├── storage/{doc_id}/
│   ├── source.pdf
│   ├── reorganized.md
│   ├── indexed.md          # when produced
│   ├── report.json
│   ├── pages/page_NNNN.txt
│   └── crops/*.png
├── .mbforge/
│   ├── library.db          # unified SQLite
│   ├── openkb/             # PageIndex + wiki + dense-rerank cache
│   └── migrations/         # archived legacy layouts
└── notes/                  # user notes
```

Path ownership:

- Library-level → `core/layout.py:LibraryLayout`
- Document-level → `core/artifact.py:ArtifactResolver`  
Do **not** join `storage/` / `.mbforge/` paths inline in new code.

---

## Failure cascade (summary)

| Failure | Typical impact |
|---|---|
| OCR exhausted | Empty pages → weak title/density → thin wiki |
| MolDet / MolScribe missing | `molecule_count=0`, no MoleCode / links |
| Popo / reorganize LLM fail | Warning + fallback markdown |
| PageIndex / wiki fail | Warning; molecules may still persist |
| Persist fail | Incomplete DB rows — treat as hard error for that run |

Pipeline is largely **best-effort across stages** with structured `StageResult`;
do not silently swallow errors without logging / progress events.

---

## Frontend consumption (representative)

| Endpoint area | Artifact |
|---|---|
| library document file / reorganized / report / pages | `storage/{doc_id}/…` |
| crop serving | `storage/{doc_id}/crops/…` (legacy crops fallback) |
| KB search / wiki | OpenKB under `.mbforge/openkb/` |
| moldet / coref APIs | live model path, not pipeline artifacts |

Query params and bodies use **`library_root` / `libraryRoot`** — not `project_root`.
