# PDF Type Classification & OCR Method Selection

**Date:** 2026-05-27  
**Status:** Draft  
**Scope:** PDF parsing pipeline enhancement

## Overview

Add intelligent PDF type classification to automatically select the optimal OCR method based on content type (text-based vs image-based), balancing cost, speed, and accuracy. Includes molecule detection, context extraction, and graph-based storage for OSAR design.

## Goals

1. **Efficiency** — Skip unnecessary work based on PDF type
2. **Accuracy** — Apply appropriate OCR method per page
3. **Cost optimization** — Use cheapest method that meets quality requirements
4. **User control** — Recommend but confirm before expensive operations
5. **OSAR readiness** — Store molecules with graph structures for substructure matching

---

## 1. PDF Classification Module

### Purpose

Silently determine PDF type and content in the background.

### Design Principles

- Classification runs automatically, no user interaction required
- Molecular detection is always-on by default
- Confirmation only surfaces when there's an actual decision to make
- Other tasks (text extraction, summarization) continue in parallel

### Components

```
PDFClassifier
├── classify_document(pdf_path) → DocumentClassification
│   ├── text_density: float (chars per page avg)
│   ├── is_scanned: bool (text_density < 50)
│   ├── has_molecular_patterns: bool (SMILES/chemical names detected)
│   └── metadata_hints: dict (file name, title analysis)
│
└── classify_page(page_text, page_idx) → PageClassification
    ├── text_density: float
    ├── is_scanned: bool
    └── context_from_neighbors: str (text from adjacent pages)
```

### Classification Rules

- **Document-level:** `text_density < 50` → scanned PDF
- **Page-level:** `len(page_text.strip()) < 20` → image page
- **Molecular detection:** regex for SMILES patterns + chemical name dictionary
- **Metadata heuristic:** file name/title analysis

### Flow

```
PDF Input
  │
  ├─ [Background, immediate]
  │   ├── Metadata scan (file name, title)
  │   ├── Text density check (PyMuPDF get_text)
  │   └── Text pattern scan (SMILES/chemical names)
  │
  ├─ [Background, after text extraction]
  │   ├── Page-level classification
  │   └── OCR method recommendation
  │
  └─ [UI, after indexing complete]
      └── Molecule Review Panel
```

---

## 2. Molecule Review Panel (Web Stack)

### Purpose

Let users review, confirm, and manually adjust detected molecules.

### Frontend Components

| Component | Technology |
|-----------|------------|
| Molecule display | RDKit.js (via `@rdkit/rdkit`) or SmilesDrawer |
| Interactive editor | Ketcher (open source) or MolDrawJS |
| Canvas rendering | SVG/Canvas via molecule library |
| State management | React hooks + context |

### Panel Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Molecule Detection Results                    [Approve All] │
├─────────────────────────────────────────────────────────────┤
│  Page 3: 2 molecules detected                              │
│  ┌─────────────┐  ┌─────────────┐                          │
│  │  [RDKit.js] │  │  [RDKit.js] │                          │
│  │  CC(=O)Oc.. │  │  c1ccc(C=.. │                          │
│  │  Conf: 0.92 │  │  Conf: 0.87 │                          │
│  │  [Accept]   │  │  [Accept]   │                          │
│  └─────────────┘  └─────────────┘                          │
│                                                             │
│  Page 5: 1 molecule detected (low confidence)              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  [Ketcher Editor Canvas]                            │   │
│  │  - Draw/edit molecule structure                     │   │
│  │  - Add/remove atoms and bonds                       │   │
│  │  - Import/export SMILES                             │   │
│  └─────────────────────────────────────────────────────┘   │
│  SMILES: CC1=CCC..  [Update] [Accept] [Reject]            │
└─────────────────────────────────────────────────────────────┘
```

### Features

1. **Image + SMILES display** — cropped molecule image alongside detected SMILES
2. **Confidence indicator** — highlight low-confidence detections (< 0.6)
3. **Per-molecule actions:**
   - Accept → save to database
   - Reject → discard
   - Edit → open interactive molecule editor
4. **Manual add** — draw/enter SMILES for missed molecules
5. **Batch actions:**
   - Approve All → accept all detections
   - Reject All → discard all
   - Export JSON → save for external review

### Interactive Editing

- **Ketcher** — full-featured chemical editor, `ketcher-react` npm package
- **RDKit.js** — WebAssembly port, `@rdkit/rdkit` npm package

---

## 3. OCR Method Router

### Purpose

Select and execute the appropriate OCR method based on classification.

### OCR Methods

| Method | ID | Cost | Speed | Capabilities |
|--------|-----|------|-------|--------------|
| Expensive API | `api_full` | High | Fast | Text + esmiles (molecules) |
| Cheap API | `api_text` | Low | Fast | Text only, preserves images |
| Local Pipeline | `local` | Free | Very slow | Text + MoldetV2 + custom model |
| VLM Fallback | `vlm` | Low | Medium | Reads entire page |

### Router Logic

```python
class OCRMethodRouter:
    def select_method(
        self, 
        classification: DocumentClassification,
        page_classification: PageClassification,
        user_settings: ProjectSettings,
    ) -> OCRMethod:
        
        # 1. User override (if set in project settings)
        if user_settings.ocr_method_override:
            return user_settings.ocr_method_override
        
        # 2. Auto-select based on content
        if page_classification.is_scanned:
            if page_classification.has_molecular_context:
                return OCRMethod.API_FULL
            else:
                return OCRMethod.API_TEXT
        else:
            return OCRMethod.API_TEXT
```

### Execution Flow

```
For each page:
  │
  ├─ Router selects method
  │
  ├─ Execute OCR method
  │   ├── api_full → call external API (text + esmiles)
  │   ├── api_text → call external API (text only)
  │   ├── local → run local pipeline (text + MoldetV2)
  │   └── vlm → call VLM API
  │
  ├─ Collect results
  │   ├── text_content: str
  │   ├── molecules: list[MoleculeResult]
  │   └── images: list[Path]
  │
  └─ Pass to LLM formatting
```

### Cost Estimation

```python
def estimate_cost(method: OCRMethod, page_count: int) -> dict:
    return {
        "method": method,
        "pages": page_count,
        "estimated_cost_usd": PAGE_COST[method] * page_count,
        "estimated_time_seconds": PAGE_TIME[method] * page_count,
    }
```

---

## 4. Post-processing & Molecule Storage

### eSMILES Standardization

All molecules stored in canonical eSMILES format.

### Molecule-Context Extraction

Extract all text passages mentioning each molecule:
- Direct SMILES mentions
- Chemical name mentions
- Activity data (IC50, EC50, etc.)

### Graph Structure Storage

```python
class MoleculeGraphStorage:
    def store_molecule(self, molecule: MoleculeRecord):
        mol = Chem.MolFromSmiles(molecule.esmiles)
        graph = self._mol_to_graph(mol)
        mcs_fingerprint = self._compute_mcs_fingerprint(mol)
        # Store in database
```

### MCS (Maximum Common Substructure)

```python
class MCSAnalyzer:
    def find_mcs(self, molecules: list[str]) -> MCSResult:
        mols = [Chem.MolFromSmiles(s) for s in molecules]
        mcs = rdFMCS.FindMCS(mols, completeRingsOnly=True, matchChirality=True)
        return MCSResult(smiles=mcs.smartsString, ...)
```

### Storage Schema

```sql
CREATE TABLE molecules (
    id INTEGER PRIMARY KEY,
    esmiles TEXT NOT NULL UNIQUE,
    name TEXT,
    graph_json TEXT,
    mcs_fingerprint TEXT,
    atom_count INTEGER,
    bond_count INTEGER,
    ring_count INTEGER,
    source_doc TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE molecule_contexts (
    id INTEGER PRIMARY KEY,
    molecule_id INTEGER REFERENCES molecules(id),
    context_text TEXT,
    context_type TEXT,
    page_idx INTEGER,
    position_start INTEGER,
    position_end INTEGER
);

CREATE TABLE mcs_cache (
    id INTEGER PRIMARY KEY,
    molecule_set_hash TEXT,
    mcs_smarts TEXT,
    mcs_atom_count INTEGER,
    mcs_bond_count INTEGER,
    coverage_json TEXT
);
```

---

## 5. Confirmation Panel & User Interaction

### When Confirmation Appears

1. After PDF indexing completes (not during)
2. Only if there are ambiguous decisions or expensive methods selected
3. User can dismiss and review later via project panel

### Panel Layout

```
┌─────────────────────────────────────────────────────────────┐
│  PDF Classification Results           [Proceed] [Override]  │
├─────────────────────────────────────────────────────────────┤
│  Document Type: Mixed (Text + Scanned)                      │
│  Total Pages: 12                                            │
│                                                             │
│  Page Map: [T][T][T][S][S][T][T][S][S][T][T][T]           │
│                                                             │
│  Recommended Methods:                                       │
│  - Text pages (8): Cheap API                                │
│  - Scanned + molecules (3): Expensive API                   │
│  - Scanned no molecules (1): Cheap API                      │
│                                                             │
│  Estimated cost: $0.45                                      │
│  Detected Molecules: 5                                      │
│                                                             │
│  Actions: [Review Molecules] [Override Methods]             │
└─────────────────────────────────────────────────────────────┘
```

### User Workflow

```
1. User drops PDF into project
2. Pipeline starts automatically (background)
3. After indexing completes:
   ├── If no ambiguities → silently complete
   └── If ambiguities → show confirmation panel
4. User reviews:
   ├── Accept recommendations → proceed
   ├── Override methods → re-run
   └── Review molecules → open Molecule Review Panel
5. Molecules saved with graph structures
```

### Project Settings

```json
{
  "ocr": {
    "method_override": null,
    "auto_classify": true,
    "show_confirmation": true,
    "molecule_review_required": true
  }
}
```

---

## Implementation Notes

### Files to Create

1. `src/mbforge/parsers/pdf_classifier.py`
2. `src/mbforge/parsers/ocr_router.py`
3. `src/mbforge/parsers/post_processor.py`
4. `src/mbforge/parsers/molecule_context.py`
5. `src/mbforge/core/molecule_graph.py`
6. `src/mbforge/core/mcs_analyzer.py`
7. `frontend/src/components/MoleculeReviewPanel.tsx`
8. `frontend/src/components/MoleculeEditor.tsx`

### Dependencies

- `@rdkit/rdkit` — RDKit.js for molecule rendering
- `ketcher-react` — Interactive molecule editor

### Testing

1. Unit tests for PDFClassifier
2. Unit tests for OCRMethodRouter
3. Integration tests for molecule extraction + storage
4. E2E tests for review panel
