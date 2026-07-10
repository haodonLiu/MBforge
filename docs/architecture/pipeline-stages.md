# MBForge Pipeline — Full Path Reference

> **Last verified:** 2026-07-10  
> **Pipeline version:** 9 stages + 2 optional sub-steps  
> **Entry point:** `mbforge.pipeline.runner.run_pipeline()`

## At a glance

```
PDF → extract → density → rough_md → detect → insert_molecode → [popo] → reorganize → pageindex → wiki → persist_mols → register_links → persist
```

Each stage emits events (`start` / `progress` / `complete` / `warning`) that flow back
to the caller via the optional `on_progress` callback. All stages are sequential and
in-process — no external queue or worker pool.

---

## Stage table

| # | Stage | Key code | Purpose | Output / Side effect |
|---|---|---|---|---|
| 1 | **extract** | `extract_text.extract_pdf_text()` | PyMuPDF native + OCR fallback (MinerU → PaddleOCR → GLM-OCR → RapidOCR) for pages with <50 native chars | `ExtractedDocument{raw_text, pages[], title, parser}` |
| 2 | **density** | `classify.classify_density()` | Classify doc kind (text_only / mixed / image_only) + chars/page | `DensityClassification{doc_kind, pages_needing_ocr, avg_text_density}` |
| 3a | **rough_md** | `extract_text.write_rough_markdown()` | Per-page text → rough markdown with `<!-- PAGE N -->` separators | temp file `/tmp/rough.md` |
| 3b | **detect** | `extract_molecules.extract_molecules_from_pdf()` + `normalize.normalize_molecules()` | MolDetv2-FT bbox → MolScribe → RDKit validate → element whitelist → dedup | `molecule_stats{candidates[], molecule_count, rejected_count}` |
| 3c | **insert_molecode** | `organizer.insert_molecode_blocks()` | Insert MoleCode blocks at bbox-matched text positions, fallback to page-end | temp file `/tmp/enriched.md` |
| 3d-0 | **popo** (optional) | `backends.popo.popo_postprocess_markdown()` | MinerU-Popo: LLM section enhancement. Gated by `popo.enabled` config | rewrites `/tmp/enriched.md` in place |
| 3d | **reorganize** | `organizer.reorganize_with_llm()` | LLM reorganize with chunking. Degeneracy detector (`_looks_degenerate`) → rule-based fallback | `storage/{doc_id}/reorganized.md` |
| — | _(side-effect)_ | `shutil.copy2(pdf_path, storage/{doc_id}/source.pdf)` | Make source PDF accessible from storage dir (frontend serves it via `/api/v1/library/documents/{doc_id}/file`) | `storage/{doc_id}/source.pdf` |
| 3e | **pageindex** | `openkb.adapter.OpenKBAdapter.index_markdown()` | Build hierarchical PageIndex tree from reorganized.md | OpenKB doc entry `openkb/documents/{doc_id}.md` |
| 4 | **wiki** | `adapter.compile_wiki()` | LLM-compile summary / concepts / entities | `openkb/wiki/{summaries,concepts,entities}/*.md` |
| 5 | **persist_mols** | `_persist_molecules()` → `persist_molecules.persist_molecule_candidates()` | Write molecule records to SQLite `molecules.db` | rows in `molecules` table |
| 6 | **register_links** | `organizer.register_molecules_from_text()` | Walk reorganized.md MoleCode blocks, link each to source page via `%% page=N` comment | rows in `text_molecule_links` table |
| 7 | **persist** | `_persist_document()` | Write `report.json` + per-page text files | `storage/{doc_id}/{report.json, pages/page_NNNN.txt}` |

After stage 7: cleanup `rough.md` + `enriched.md` temp files. `reorganized.md` stays.

---

## Per-stage inputs / outputs

### Stage 1 — extract

**Input:** `pdf_path: str`, `ocr_config: dict | None`

**Logic flow** (`extract_text.py:53-128`):
1. `fitz.open(pdf_path)`, iterate pages.
2. For each page, `page.get_text("text").strip()`.
3. If `<50 chars` → push to `pages_needing_ocr`.
4. After native pass, call `_ocr_pages(doc, page_indices, ocr_config)`.
5. `_ocr_pages`:
   - Read `ocr.upload_batch_size` (default 50, configured to 1 for backends without batch API).
   - If batch > 1 AND MinerU configured: try batch path.
   - Else: per-page loop with **retry-with-backoff** (3 attempts, 1s/3s/9s).
6. Fill OCR text back into `pages[idx].text`, append to `full_text_parts`.
7. Extract title via `_extract_title()` from page 1 OCR.

**Output:** `ExtractedDocument(raw_text, page_count, parser, title, pages[])`

**Failure modes:**
- OCR backends transient timeout → retried (post-P0)
- All 3 attempts exhausted → page text stays empty → cascade: `title=null`, `image_only`, no headings

### Stage 2 — density

**Input:** `pages: list[PageContent]`

**Logic** (`classify.py:36-58`):
- `need_ocr = sum(1 for p in pages if p.needs_ocr)`
- `total_text = sum(len(p.text) for p in pages)`
- Classification thresholds:
  - `need_ocr/len > 0.9 AND total_text < 1000` → `image_only`
  - `need_ocr/len > 0.1` → `mixed`
  - else → `text_only`
- `avg_text_density = total_text / max(len(pages), 1)` (chars/page — fixed from previous divide-by-near-zero bug)

**Output:** `DensityClassification(doc_kind, page_count, pages_needing_ocr, avg_text_density)`

**Downstream effect:** `text_only` without molecules skips `reorganize` (LLM step skipped, copy enriched.md directly).

### Stage 3a — rough_md

**Input:** `pages: list[PageContent]`, `output_path: str`

**Logic** (`extract_text.py:write_rough_markdown`):
- For each page: prepend `<!-- PAGE N -->` separator, write text lines.
- Detect heading-like lines via `HEADING_PATTERNS` regex (Abstract, Background, Methods, etc., digit-prefixed lines).
- Promote detected lines to `#` / `##` markdown headings.

**Output:** temp `.md` file at `tempfile.mktemp(suffix=".md")`.

### Stage 3b — detect

**Input:** `pdf_path`, `project_root`, `doc_id`, `density`

**Logic** (`extract_molecules.extract_molecules_from_pdf` + `normalize.normalize_molecules`):
1. Auto-deploy model via `ResourceManager.ensure("moldet")` (downloads from ModelScope `haodont/Moldetv2_FT_coref`).
2. Load MolDetv2-FT detector, MolScribe.
3. Render each page at `detection_dpi` (default 200).
4. **Skip rule:** page has `> 500 native chars` AND no embedded images → skip (text-only page).
5. Detect molecules: `detect_coref_via_ft_detector(image)` returns `CorefResult{bboxes, corefs}`.
6. For each bbox `category_id=1` (mol): crop, preprocess (white-bg binarization → DBSCAN), run `molscribe.predict(crop)` → SMILES.
7. Save crop PNG to `{project_root}/.mbforge/crops/{doc_id}/`.
8. **Normalize** (`normalize.py`):
   - Reject empty / numeric / <3 char fragments (`_is_unusable_fragment`).
   - RDKit parse → canonical SMILES.
   - **Element whitelist** (`C/N/O/S/halides/P/B/Si/Se/As/H/*`) → reject Re/Rf/etc. as `invalid_element`.
   - Dedup by canonical SMILES.
9. Return `molecule_stats{candidates[], molecule_count, rejected_count, ...}`.

**Output:** `ExtractionResult[]` normalized to `NormalizedMolecule[]`.

**Failure modes:**
- MolDet model missing → early return `[]`, `molecule_count=0`
- All molecules filtered out by RDKit / element check → `molecule_count=0`
- Over-segmentation on dense figure pages → many false positives (page 17: 26 from ~10 visible)

### Stage 3c — insert_molecode

**Input:** `rough_md_path`, `pages[]`, `candidates: list[NormalizedMolecule]`, `output_path`

**Logic** (`organizer.insert_molecode_blocks:144-211`):
- For each non-rejected mol:
  - `page_idx = detections[0].page`
  - Find best line position via `_find_position_in_pages(page_idx, bbox, pages)` (IoU overlap with text spans).
  - If overlap found → insert just after that span.
  - Else → append at page-end with `<!-- Molecule {name} (Page {page_num}) -->` annotation.
  - Fallback: append at end of file.
- Build MoleCode block via `_mol_to_molecode(smiles, name, page_num)`:
  - Convert SMILES → RDKit Mol → Mermaid graph via `molecode.mol_to_mermaid`.
  - Inject `%% page={N}` mermaid comment as first line (used by frontend to jump PDF page).
  - Wrap in ` ```molecode ... ``` ` fenced block.

**Output:** temp `enriched.md` (rough md + MoleCode blocks at semantic positions).

### Stage 3d-0 — popo (optional)

**Trigger:** `cfg.popo.enabled == True` AND `MinerU-Popo installed`.

**Logic** (`backends/popo.py:popo_postprocess_markdown`):
- Reads `enriched.md`, invokes MinerU-Popo LLM driver (4B Qwen3-VL with `chat_template.jinja` injected to work around upstream bug).
- LLM enhances section headings, table continuation, figure caption association.
- Rewrites `enriched.md` in place.

**Failure:** any exception → log warning, continue with `enriched.md` unchanged. Popo never crashes pipeline.

### Stage 3d — reorganize

**Input:** `enriched_md_path`, `output_path = storage/{doc_id}/reorganized.md`, `model`

**Logic** (`organizer.reorganize_with_llm:264-379`):
1. Read md, `estimated_tokens = len(md) // 4`.
2. **Short path** (`< 4000 tokens`):
   - Single LLM call: `reorganize_with_llm` prompt + document.
   - Check 1: `len(response) < len(input) * 0.5` → degenerate (LLM summarized), fallback.
   - Check 2: `_looks_degenerate(response, original)` → strips MoleCode or >75% shingle repetition → fallback.
   - Fallback = `_rule_based_reorganize`: regex-detect patent sections (Abstract, Background, Summary, Detailed Description, Claims), promote ALL-CAPS lines to headings.
3. **Long path** (>= 4000 tokens):
   - Split on `molecode` blocks (preserve blocks intact).
   - Chunk to ~6000 tokens each.
   - Run LLM per chunk.
   - If total output < 50% input → fallback.
   - Else run `_looks_degenerate` on joined chunks → fallback if degenerate.

**Output:** `storage/{doc_id}/reorganized.md` (real headings + 34 MoleCode blocks with `%% page=N`).

**Side-effect (between 3d and 3e):** copy `pdf_path` → `storage/{doc_id}/source.pdf` (frontend serves it via `/api/v1/library/documents/{doc_id}/file`).

### Stage 3e — pageindex

**Input:** `reorganized.md`, `doc_id`

**Logic** (`openkb/adapter.py:OpenKBAdapter.index_markdown`):
- Walk markdown, build hierarchical tree (zero LLM, regex-based).
- Write `openkb/documents/{doc_id}.md` (132KB for 20-page patent).
- Write tree index files.

**Output:** `openkb_doc_id` (string), `indexed_count=1`.

**Failure:** any exception → log warning, `indexed_count=0`, `openkb_doc_id=""`. Wiki stage then skipped.

### Stage 4 — wiki

**Trigger:** `openkb_doc_id != ""`.

**Logic** (`adapter.compile_wiki(doc_name, doc_id, page_count)`):
- LLM-compile `summary` (whole-doc), `concepts` (cross-doc topics), `entities` (named entities).
- Async (`asyncio.run`); writes `.md` files to `openkb/wiki/{summaries,concepts,entities}/`.

**Output:** `WO2026035726A1_20pg.md` summary, plus per-entity / per-concept markdown.

**Failure:** any exception → warning, continue. Wiki is non-blocking.

### Stage 5 — persist_mols

**Input:** `molecule_stats.candidates[]`

**Logic** (`persist_molecules.persist_molecule_candidates`):
- Write molecule records to `molecules.db` (SQLite, table `molecules`).
- Stores: canonical_smiles, esmiles, name, status, reject_reason, sources, properties.
- Each candidate gets `id`, persisted with `doc_id` association.

**Output:** rows in `molecules` table, row per candidate.

### Stage 6 — register_links

**Input:** `reorganized.md`, `candidates[]`, `doc_id`, `project_root`

**Logic** (`organizer.register_molecules_from_text`):
- Walk reorganized.md, find MoleCode blocks.
- For each block:
  - Read `%% page=N` comment.
  - Match by name OR canonical_smiles.
  - Insert `text_molecule_links(doc_id, molecule_id, page, position)` row.
- Skips `status=rejected` candidates.

**Output:** rows in `text_molecule_links` table (enables "click molecule → jump page" in frontend).

### Stage 7 — persist

**Input:** `extracted`, `density`, `molecule_stats`

**Logic** (`_persist_document`):
- For each page with text, write `storage/{doc_id}/pages/page_{NNNN}.txt`.
- Write `storage/{doc_id}/report.json`:
  ```json
  {
    "doc_id": "...",
    "page_count": 20,
    "parser": "pymupdf+ocr",
    "title": "...",
    "doc_kind": "mixed",
    "avg_text_density": 1933.0,
    "pages_needing_ocr": 20,
    "molecule_count": 34,
    "molecule_pending_review_count": 0,
    "molecule_rejected_count": 0,
    "molecule_sources": ["image"],
    "kb_backend": "openkb"
  }
  ```

---

## Side-effect summary (final filesystem state)

After pipeline run completes, the following artifacts exist:

```
{project_root}/
├── storage/
│   └── {doc_id}/
│       ├── source.pdf             # COPY of input PDF (frontend file endpoint)
│       ├── reorganized.md         # LLM/rule-based reorganized markdown with MoleCode blocks
│       ├── report.json            # pipeline summary
│       └── pages/
│           ├── page_0001.txt      # per-page OCR/native text
│           ├── page_0002.txt
│           └── ...
├── .mbforge/
│   ├── crops/
│   │   └── {doc_id}/
│   │       ├── {doc_id}_page_0000_mol_0000.png   # molecule crops
│   │       └── ...
│   └── openkb/
│       ├── documents/
│       │   └── {doc_id}.md        # PageIndex-tree indexed markdown
│       └── wiki/
│           ├── summaries/
│           │   └── {doc_id}.md
│           ├── concepts/
│           │   └── *.md
│           └── entities/
│               └── *.md
└── index/
    ├── knowledge_base.db          # page-text + report storage
    └── molecules.db               # molecules + text_molecule_links
```

Temp files `rough.md` and `enriched.md` in `tempfile.gettempdir()` are cleaned at end.

---

## Failure cascade table

| Stage fails | Downstream impact |
|---|---|
| OCR transient (now retried 3x) | If all retries fail: `title=null`, `doc_kind=image_only`, no headings, no wiki. |
| MolDet model missing | `molecule_count=0`, no MoleCode blocks, no molecule links. |
| All molecules rejected (RDKit / element whitelist) | Same as above. |
| Popo LLM fails | Warning, continue with enriched.md unchanged. |
| Reorganize LLM collapses | `_looks_degenerate` triggers rule-based fallback → section headings still emerge from regex. |
| PageIndex fails | Wiki skipped. Molecules persist normally. |
| Wiki fails | Warning. PageIndex + molecules persist normally. |
| Molecule persist fails | Warning, no rows in `molecules` table. |
| Source PDF copy fails | Debug log only, doesn't affect any other stage. |

Pipeline is **best-effort cascade**: each stage independent, failures don't crash later stages.

---

## Frontend consumption map

The frontend (`DocumentViewer.tsx` + `library.ts` + `kb.ts` wrappers) consumes:

| Backend endpoint | Source artifact |
|---|---|
| `GET /api/v1/library/documents/{doc_id}/file` | `storage/{doc_id}/source.pdf` |
| `GET /api/v1/library/documents/{doc_id}/reorganized` | `storage/{doc_id}/reorganized.md` |
| `GET /api/v1/library/documents/{doc_id}/report` | `storage/{doc_id}/report.json` |
| `GET /api/v1/library/documents/{doc_id}/pages/{page}` | `storage/{doc_id}/pages/page_{NNNN}.txt` |
| `GET /api/v1/library/documents/{doc_id}/crop?rel_path=...` | `.mbforge/crops/{doc_id}/...` |
| `GET /api/v1/library/documents/{doc_id}/indexed-md` | `.mbforge/openkb/documents/{doc_id}.md` |
| `GET /api/v1/kb/wiki/list?project_root=...` | lists `wiki/{summaries,concepts,entities}/*.md` |
| `GET /api/v1/kb/wiki/summary?doc_id=...` | `wiki/summaries/{doc_id}.md` |
| `GET /api/v1/kb/wiki/concept?name=...` | `wiki/concepts/{name}.md` |
| `GET /api/v1/kb/wiki/entity?name=...` | `wiki/entities/{name}.md` |

Frontend `MoleCode` block click reads `%% page=N` comment (set by stage 3c) and calls `pdfViewerRef.setCurrentPage(N)`.