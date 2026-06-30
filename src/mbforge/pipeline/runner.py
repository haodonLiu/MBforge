"""Pipeline runner — orchestrates document processing via OpenKB + PageIndex.

Stages:
1. Extract: PDF text extraction (PyMuPDF + OCR fallback)
2. PageIndex: Tree index via LLM reasoning
3. Wiki: Compile summaries, concepts, entities
4. Enrich: Molecule detection from figures (MolDet)
5. Persist: Save page texts + report to filesystem
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..utils.helpers import ensure_dir, save_json
from ..utils.logger import get_logger

logger = get_logger("mbforge.pipeline.runner")


@dataclass
class PipelineEvent:
    stage: str
    event: str  # start, progress, complete, warning, failed
    message: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class PipelineResult:
    doc_id: str
    page_count: int
    section_count: int
    chunk_count: int
    indexed_count: int
    parser: str
    title: str | None = None
    duration_ms: int = 0


ProgressCallback = Callable[[PipelineEvent], None]


def run_pipeline(
    pdf_path: str,
    project_root: str,
    doc_id: str = "",
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    on_progress: ProgressCallback | None = None,
) -> PipelineResult:
    """Run the document processing pipeline via OpenKB.

    Args:
        pdf_path: Path to the PDF file
        project_root: Project root directory
        doc_id: Document ID (auto-generated from filename if empty)
        chunk_size: Ignored (kept for API compat)
        chunk_overlap: Ignored (kept for API compat)
        on_progress: Progress callback

    Returns:
        PipelineResult with processing statistics
    """
    if not doc_id:
        doc_id = Path(pdf_path).stem

    start_time = time.monotonic()

    def _emit(event: str, message: str = "", **data):
        if on_progress:
            on_progress(
                PipelineEvent(stage="pipeline", event=event, message=message, data=data)
            )
        logger.info("[%s] %s", event, message)

    _emit("start", f"Processing {Path(pdf_path).name}")

    # Stage 1: Extract
    _emit("progress", "Extracting text...", stage="extract")
    from .extract_text import extract_pdf_text

    extracted = extract_pdf_text(pdf_path)
    _emit(
        "complete",
        f"Extracted {extracted.page_count} pages ({len(extracted.raw_text)} chars)",
        stage="extract",
    )

    # Stage 2: PageIndex tree indexing
    _emit("progress", "Building PageIndex tree...", stage="pageindex")
    from ..openkb.adapter import OpenKBAdapter

    adapter = OpenKBAdapter(project_root)
    openkb_doc_id = adapter.index_document(pdf_path, doc_id)
    _emit("complete", f"PageIndex tree built: {openkb_doc_id}", stage="pageindex")

    # Stage 3: Wiki compilation
    _emit("progress", "Compiling wiki...", stage="wiki")
    doc_name = Path(pdf_path).stem
    import asyncio

    asyncio.run(adapter.compile_wiki(doc_name, doc_id, extracted.page_count))
    _emit("complete", "Wiki compiled", stage="wiki")

    # Stage 4: Enrich (molecule detection)
    _emit("progress", "Detecting molecules...", stage="enrich")
    enrich_result = _enrich_molecules(
        pdf_path, project_root, doc_id, extracted.page_count
    )
    _emit(
        "complete",
        f"Detected {enrich_result.get('molecule_count', 0)} molecules",
        stage="enrich",
    )

    # Stage 5: Persist
    _emit("progress", "Saving document...", stage="persist")
    _persist_document(project_root, doc_id, extracted, enrich_result)
    _emit("complete", "Document saved", stage="persist")

    duration_ms = int((time.monotonic() - start_time) * 1000)
    _emit("complete", f"Pipeline finished in {duration_ms}ms")

    return PipelineResult(
        doc_id=doc_id,
        page_count=extracted.page_count,
        section_count=0,
        chunk_count=0,
        indexed_count=1,
        parser=extracted.parser,
        title=extracted.title,
        duration_ms=duration_ms,
    )


def _enrich_molecules(
    pdf_path: str,
    project_root: str,
    doc_id: str,
    page_count: int,
) -> dict[str, Any]:
    """Detect molecules in PDF figures using MolDet."""
    try:
        from ..backends import moldet

        pipeline = moldet.get_moldet()
        if pipeline is None or not pipeline.is_available():
            return {"molecule_count": 0, "skipped": True, "reason": "no GPU"}

        import fitz

        doc = fitz.open(pdf_path)
        all_molecules: list[dict] = []
        try:
            for page_idx in range(min(page_count, 10)):
                page = doc.load_page(page_idx)
                zoom = 300 / 72.0
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)

                import numpy as np
                from PIL import Image

                img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width, pix.n
                )
                image = Image.fromarray(img_array)

                boxes = pipeline.doc_detector.detect(image)
                for box in boxes:
                    x1, y1, x2, y2, conf = box
                    all_molecules.append(
                        {
                            "page": page_idx + 1,
                            "bbox": [x1, y1, x2, y2],
                            "confidence": conf,
                        }
                    )
        finally:
            doc.close()

        return {"molecule_count": len(all_molecules), "molecules": all_molecules}
    except Exception as e:
        logger.warning("Molecule enrichment failed: %s", e)
        return {"molecule_count": 0, "error": str(e)}


def _persist_document(
    project_root: str,
    doc_id: str,
    extracted,
    enrich_result: dict,
) -> None:
    """Save page texts and report to filesystem."""
    root = Path(project_root)

    pages_dir = root / "index" / "pages" / doc_id
    ensure_dir(pages_dir)
    for page in extracted.pages:
        page_file = pages_dir / f"page_{page.page_num:04d}.txt"
        page_file.write_text(page.text, encoding="utf-8")

    report_dir = root / "projects" / doc_id
    ensure_dir(report_dir)
    report = {
        "doc_id": doc_id,
        "page_count": extracted.page_count,
        "parser": extracted.parser,
        "title": extracted.title,
        "molecule_count": enrich_result.get("molecule_count", 0),
        "kb_backend": "openkb",
    }
    save_json(report_dir / "report.json", report)
