# pdf-inspector Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate pdf-inspector as Tauri commands to replace PDFClassifier and improve text extraction quality.

**Architecture:** pdf-inspector (Rust) is called via Tauri commands. Python pipeline calls Tauri commands via HTTP (transition period). Frontend calls via `invoke()`. Fallback to PyMuPDF + PDFClassifier when Tauri unavailable.

**Tech Stack:** Rust (pdf-inspector, tauri 2, serde), Python (requests, fastapi), TypeScript (@tauri-apps/api)

---

## File Structure

| File | Operation | Purpose |
|------|-----------|---------|
| `src-tauri/Cargo.toml` | Modify | Add pdf-inspector + regex deps |
| `src-tauri/src/commands/pdf.rs` | Create | classify_pdf + extract_text Tauri commands |
| `src-tauri/src/commands/mod.rs` | Create | Module re-exports |
| `src-tauri/src/main.rs` | Modify | Register commands module + invoke_handler |
| `src-tauri/capabilities/default.json` | Modify | Add command permissions |
| `src/mbforge/utils/config.py` | Modify | Add use_pdf_inspector to OcrConfig |
| `src/mbforge/parsers/pdf_parser.py` | Modify | Stage 1+1.5 use Tauri commands with fallback |
| `frontend/src/api/tauri-bridge.ts` | Modify | Add classifyPdf + extractText |
| `tests/unit/parsers/test_pdf_inspector_integration.py` | Create | Python integration tests |

---

### Task 1: Rust Foundation — Cargo.toml + commands/mod.rs

**Files:**
- Modify: `src-tauri/Cargo.toml`
- Create: `src-tauri/src/commands/mod.rs`

- [ ] **Step 1: Add pdf-inspector dependency to Cargo.toml**

Read `src-tauri/Cargo.toml`, then add after the `serde_json` line:

```toml
pdf-inspector = { git = "https://github.com/firecrawl/pdf-inspector" }
regex = "1"
```

- [ ] **Step 2: Create commands/mod.rs**

Create `src-tauri/src/commands/mod.rs`:

```rust
pub mod pdf;
```

- [ ] **Step 3: Verify Cargo.toml parses**

Run: `cd src-tauri && cargo check 2>&1 | head -5`
Expected: may fail with "unresolved import commands" (main.rs doesn't know about it yet), but Cargo.toml should parse.

- [ ] **Step 4: Commit**

```bash
git add src-tauri/Cargo.toml src-tauri/src/commands/mod.rs
git commit -m "chore: add pdf-inspector dependency and commands module skeleton"
```

---

### Task 2: Rust Command — classify_pdf

**Files:**
- Create: `src-tauri/src/commands/pdf.rs`

- [ ] **Step 1: Write the classify_pdf command**

Create `src-tauri/src/commands/pdf.rs`:

```rust
use serde::Serialize;

#[derive(Serialize)]
pub struct PdfClassification {
    pub pdf_type: String,
    pub confidence: f64,
    pub page_count: usize,
    pub pages_needing_ocr: Vec<usize>,
    pub text_density_avg: f64,
}

#[tauri::command]
pub fn classify_pdf(path: String) -> Result<PdfClassification, String> {
    let result = pdf_inspector::detect_pdf(&path)
        .map_err(|e| format!("pdf-inspector detect failed: {}", e))?;

    let pdf_type = match result.pdf_type {
        pdf_inspector::PdfType::TextBased => "TextBased",
        pdf_inspector::PdfType::Scanned => "Scanned",
        pdf_inspector::PdfType::Mixed => "Mixed",
        pdf_inspector::PdfType::ImageBased => "ImageBased",
    };

    Ok(PdfClassification {
        pdf_type: pdf_type.to_string(),
        confidence: result.confidence,
        page_count: result.page_count,
        pages_needing_ocr: result.pages_needing_ocr,
        text_density_avg: result.text_density_avg,
    })
}
```

Note: The exact pdf-inspector API may differ. Check `pdf_inspector` crate docs or source at `https://github.com/firecrawl/pdf-inspector` for actual struct/enum names. Adjust field names and match arms accordingly.

- [ ] **Step 2: Verify Rust compiles**

Run: `cd src-tauri && cargo check 2>&1 | tail -10`
Expected: should compile or show type mismatches to fix.

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/commands/pdf.rs
git commit -m "feat(rust): add classify_pdf Tauri command"
```

---

### Task 3: Rust Command — extract_text

**Files:**
- Modify: `src-tauri/src/commands/pdf.rs`

- [ ] **Step 1: Add extract_text command**

Append to `src-tauri/src/commands/pdf.rs`:

```rust
#[derive(Serialize)]
pub struct PdfExtraction {
    pub markdown: String,
    pub page_texts: Vec<String>,
    pub page_count: usize,
}

#[tauri::command]
pub fn extract_text(path: String) -> Result<PdfExtraction, String> {
    let result = pdf_inspector::process_pdf(&path)
        .map_err(|e| format!("pdf-inspector process failed: {}", e))?;

    let markdown = result.markdown.unwrap_or_default();
    let page_texts: Vec<String> = result.pages.iter()
        .map(|p| p.text.clone())
        .collect();
    let page_count = result.pages.len();

    Ok(PdfExtraction {
        markdown,
        page_texts,
        page_count,
    })
}
```

Again, adjust based on actual pdf-inspector API. The key output is markdown + per-page texts.

- [ ] **Step 2: Verify Rust compiles**

Run: `cd src-tauri && cargo check 2>&1 | tail -10`

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/commands/pdf.rs
git commit -m "feat(rust): add extract_text Tauri command"
```

---

### Task 4: Register Commands in main.rs

**Files:**
- Modify: `src-tauri/src/main.rs`

- [ ] **Step 1: Add mod commands and invoke_handler**

In `src-tauri/src/main.rs`, after the `#![cfg_attr(...)]` line, add:

```rust
mod commands;
```

In the `tauri::Builder::default()` chain, add `.invoke_handler(...)` before `.setup(...)`:

```rust
.invoke_handler(tauri::generate_handler![
    commands::pdf::classify_pdf,
    commands::pdf::extract_text,
])
```

- [ ] **Step 2: Verify full Rust build**

Run: `cd src-tauri && cargo check 2>&1 | tail -10`
Expected: clean compile or minor fixes needed.

- [ ] **Step 3: Commit**

```bash
git add src-tauri/src/main.rs
git commit -m "feat(rust): register pdf commands in Tauri builder"
```

---

### Task 5: Tauri Permissions

**Files:**
- Modify: `src-tauri/capabilities/default.json`

- [ ] **Step 1: Add command permissions**

Edit `src-tauri/capabilities/default.json`:

```json
{
  "$schema": "../gen/schemas/desktop-schema.json",
  "identifier": "default",
  "description": "Default capabilities",
  "windows": ["main"],
  "permissions": [
    "core:default",
    "shell:default",
    "classify-pdf:allow-classify-pdf",
    "extract-text:allow-extract-text"
  ]
}
```

Note: The exact permission identifiers are auto-generated by `tauri_build`. After first `cargo build`, check `src-tauri/gen/schemas/` for actual names. If unsure, use `"*"` as wildcard during development.

- [ ] **Step 2: Commit**

```bash
git add src-tauri/capabilities/default.json
git commit -m "feat(rust): add Tauri command permissions"
```

---

### Task 6: Python Config — use_pdf_inspector

**Files:**
- Modify: `src/mbforge/utils/config.py`

- [ ] **Step 1: Add use_pdf_inspector to OcrConfig**

In `src/mbforge/utils/config.py`, find the `OcrConfig` dataclass and add:

```python
use_pdf_inspector: bool = True
```

- [ ] **Step 2: Verify config loads**

Run: `uv run python -c "from mbforge.utils.config import OcrConfig; c = OcrConfig(); print(c.use_pdf_inspector)"`
Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add src/mbforge/utils/config.py
git commit -m "feat(config): add use_pdf_inspector setting to OcrConfig"
```

---

### Task 7: Python Pipeline — Tauri Command Integration

**Files:**
- Modify: `src/mbforge/parsers/pdf_parser.py`

- [ ] **Step 1: Add call_tauri_command helper**

In `src/mbforge/parsers/pdf_parser.py`, add at the top (after imports):

```python
import os
import requests as _requests


def _call_tauri(command: str, **kwargs):
    """调用 Tauri command，失败时返回 None."""
    port = os.environ.get("TAURI_DEV_SERVER_PORT", "14268")
    try:
        resp = _requests.post(
            f"http://127.0.0.1:{port}/api/{command}",
            json=kwargs,
            timeout=30,
        )
        if resp.ok:
            return resp.json()
    except Exception:
        pass
    return None
```

Note: The Tauri dev server port may vary. In dev mode, Tauri v2 runs an internal API server. Check `src-tauri/tauri.conf.json` or use the `TAURI_DEV_SERVER_PORT` env var. During production, Tauri commands are called via IPC, not HTTP — this helper is a transition mechanism.

- [ ] **Step 2: Modify parse() to use Tauri commands**

In `PDFParserPipeline.parse()`, replace the Stage 1 + 1.5 block (lines ~96-144) with:

```python
        # ---- Stage 1: Text extraction ----
        # Try pdf-inspector via Tauri command first
        pdf_inspector_result = None
        classification_result = None

        from ..utils.config import load_global_config
        config = load_global_config()
        if config.ocr.use_pdf_inspector:
            pdf_inspector_result = _call_tauri("extract_text", path=str(pdf_path))
            classification_result = _call_tauri("classify_pdf", path=str(pdf_path))

        if pdf_inspector_result and classification_result:
            # pdf-inspector 路径
            content.text = pdf_inspector_result.get("markdown", "")
            text_parts = pdf_inspector_result.get("page_texts", [])
            content.metadata["pages"] = pdf_inspector_result.get("page_count", 0)
            content.metadata["classification"] = {
                "is_scanned": classification_result.get("pdf_type") in ("Scanned", "ImageBased"),
                "has_molecules": False,  # 由 Stage 5 文本正则检测
                "text_density": classification_result.get("text_density_avg", 0),
                "needs_confirmation": classification_result.get("confidence", 0) < 0.8,
                "pages_needing_ocr": classification_result.get("pages_needing_ocr", []),
            }
        else:
            # 降级：PyMuPDF + PDFClassifier（旧路径）
            if fitz is None:
                raise ImportError("PyMuPDF (fitz) 未安装，且 pdf-inspector 不可用")

            with fitz.open(str(pdf_path)) as doc:
                content.metadata["pages"] = len(doc)
                text_parts = [page.get_text() for page in doc]
            content.text = "\n\n".join(text_parts)

            from .pdf_classifier import PDFClassifier
            classifier = PDFClassifier()
            doc_classification = classifier.classify_document_from_pages(
                text_parts, metadata=content.metadata,
            )
            content.metadata["classification"] = {
                "is_scanned": doc_classification.is_scanned,
                "has_molecules": doc_classification.has_molecular_patterns,
                "text_density": doc_classification.text_density,
                "needs_confirmation": doc_classification.needs_confirmation,
                "pages": [
                    {"page_idx": p.page_idx, "is_scanned": p.is_scanned,
                     "has_molecular_patterns": p.has_molecular_patterns,
                     "text_density": p.text_density}
                    for p in doc_classification.pages
                ],
            }
```

- [ ] **Step 3: Keep PyMuPDF for image extraction (Stage 2)**

Stage 2 still needs `fitz.open()` for image extraction. Since we may have already opened the PDF in the fallback path, restructure slightly: always open fitz for Stage 2 if images are needed, but only use it for text extraction in fallback mode.

The key change: move `fitz.open()` into Stage 2 for image extraction, and keep it in the fallback path for text extraction.

- [ ] **Step 4: Verify Python imports**

Run: `uv run python -c "from mbforge.parsers.pdf_parser import PDFParserPipeline; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/mbforge/parsers/pdf_parser.py
git commit -m "feat(pipeline): integrate pdf-inspector via Tauri commands with fallback"
```

---

### Task 8: Frontend — Tauri Bridge

**Files:**
- Modify: `frontend/src/api/tauri-bridge.ts`

- [ ] **Step 1: Add classifyPdf and extractText**

Append to `frontend/src/api/tauri-bridge.ts`:

```typescript
// ---- pdf-inspector ----

export interface PdfClassification {
  pdf_type: string
  confidence: number
  page_count: number
  pages_needing_ocr: number[]
  text_density_avg: number
}

export interface PdfExtraction {
  markdown: string
  page_texts: string[]
  page_count: number
}

export async function classifyPdf(path: string): Promise<PdfClassification> {
  return invoke<PdfClassification>('classify_pdf', { path })
}

export async function extractText(path: string): Promise<PdfExtraction> {
  return invoke<PdfExtraction>('extract_text', { path })
}
```

- [ ] **Step 2: Add Rust wrappers to client.ts**

Append to `frontend/src/api/client.ts`:

```typescript
// ---- pdf-inspector Rust commands ----
import {
  isTauriAvailable,
  classifyPdf as tauriClassifyPdf,
  extractText as tauriExtractText,
  type PdfClassification,
  type PdfExtraction,
} from './tauri-bridge'

export async function classifyPdfRust(path: string): Promise<PdfClassification> {
  if (!isTauriAvailable()) throw new Error('Not in Tauri')
  return tauriClassifyPdf(path)
}

export async function extractTextRust(path: string): Promise<PdfExtraction> {
  if (!isTauriAvailable()) throw new Error('Not in Tauri')
  return tauriExtractText(path)
}
```

- [ ] **Step 3: Verify frontend builds**

Run: `cd frontend && npm run build 2>&1 | tail -5`
Expected: clean build

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/tauri-bridge.ts frontend/src/api/client.ts
git commit -m "feat(frontend): add pdf-inspector Tauri bridge functions"
```

---

### Task 9: Integration Test — Full Build Verification

**Files:**
- None (verification only)

- [ ] **Step 1: Rust build**

Run: `cd src-tauri && cargo build 2>&1 | tail -10`
Expected: successful build (may need to adjust pdf-inspector API calls based on actual crate API)

- [ ] **Step 2: Python import check**

Run: `uv run python -c "from mbforge.parsers.pdf_parser import PDFParserPipeline; from mbforge.utils.config import load_global_config; c = load_global_config(); print('pdf_inspector:', c.ocr.use_pdf_inspector)"`
Expected: `pdf_inspector: True`

- [ ] **Step 3: Frontend build**

Run: `cd frontend && npm run build 2>&1 | tail -5`
Expected: successful build

- [ ] **Step 4: Full commit of all fixes**

```bash
git add -A
git commit -m "fix: resolve compilation issues from pdf-inspector integration"
```

---

### Task 10: Documentation Update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update Architecture section in CLAUDE.md**

Add to the Architecture section:

```markdown
### pdf-inspector Integration

pdf-inspector (Rust) is integrated as Tauri commands:
- `classify_pdf`: PDF type classification (TextBased/Scanned/Mixed/ImageBased)
- `extract_text`: Structured Markdown extraction with per-page text

Python pipeline calls Tauri commands via HTTP (transition period).
Fallback to PyMuPDF + PDFClassifier when Tauri unavailable.
Config: `OcrConfig.use_pdf_inspector` (default: True)
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add pdf-inspector integration to CLAUDE.md"
```
