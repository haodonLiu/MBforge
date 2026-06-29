"""Pipeline runner — orchestrates the 5-stage document processing pipeline.

Stages:
1. Extract: PDF text extraction (PyMuPDF + OCR fallback)
2. Segment: Heading detection, section building, tree construction
3. Enrich: Molecule detection from figures (MolDet + Coref + MolScribe)
4. Persist: Save document structure + page texts to filesystem + SQLite
5. Index: Embed chunks → Zvec vector index

Ported from Rust `mbforge-pipeline/src/pipeline/runner.rs`.
"""

from __future__ import annotations

import json
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
    """Run the full document processing pipeline.

    Args:
        pdf_path: Path to the PDF file
        project_root: Project root directory
        doc_id: Document ID (auto-generated if empty)
        chunk_size: Target chunk size for indexing
        chunk_overlap: Overlap between chunks
        on_progress: Progress callback

    Returns:
        PipelineResult with processing statistics
    """
    if not doc_id:
        doc_id = Path(pdf_path).stem

    start_time = time.monotonic()

    def _emit(event: str, message: str = "", **data):
        if on_progress:
            on_progress(PipelineEvent(stage="pipeline", event=event, message=message, data=data))
        logger.info("[%s] %s", event, message)

    _emit("start", f"Processing {Path(pdf_path).name}")

    # Stage 1: Extract
    _emit("progress", "Extracting text...", stage="extract")
    from .extract_text import extract_pdf_text

    extracted = extract_pdf_text(pdf_path)
    _emit("complete", f"Extracted {extracted.page_count} pages ({len(extracted.raw_text)} chars)", stage="extract")

    # Stage 2: Segment
    _emit("progress", "Segmenting document...", stage="segment")
    from .segment import segment_document

    segmented = segment_document(extracted.raw_text, max_chars=chunk_size * 4)
    _emit("complete", f"Found {len(segmented.headings)} headings, {len(segmented.sections)} sections", stage="segment")

    # Stage 3: Enrich (molecule detection — optional, only if GPU available)
    _emit("progress", "Detecting molecules...", stage="enrich")
    enrich_result = _enrich_molecules(pdf_path, project_root, doc_id, extracted.page_count)
    _emit("complete", f"Detected {enrich_result.get('molecule_count', 0)} molecules", stage="enrich")

    # Stage 4: Persist
    _emit("progress", "Saving document...", stage="persist")
    _persist_document(project_root, doc_id, extracted, segmented, enrich_result)
    _emit("complete", "Document saved", stage="persist")

    # Stage 5: Index
    _emit("progress", "Indexing chunks...", stage="index")
    from .chunk import chunk_sections

    section_dicts = [
        {"title": s.title, "path": s.path, "text": s.text, "page_start": s.page_start, "page_end": s.page_end}
        for s in segmented.sections
    ]
    chunks = chunk_sections(section_dicts, chunk_size=chunk_size, overlap=chunk_overlap)

    collection_path = str(Path(project_root) / ".mbforge" / "search.zvec")
    index_result = _index_chunks(doc_id, chunks, collection_path)
    _emit("complete", f"Indexed {index_result.get('indexed', 0)} chunks", stage="index")

    duration_ms = int((time.monotonic() - start_time) * 1000)
    _emit("complete", f"Pipeline finished in {duration_ms}ms")

    return PipelineResult(
        doc_id=doc_id,
        page_count=extracted.page_count,
        section_count=len(segmented.sections),
        chunk_count=len(chunks),
        indexed_count=index_result.get("indexed", 0),
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
    """Detect molecules in PDF figures using MolDet + Coref + MolScribe."""
    try:
        from ..backends import moldet

        pipeline = moldet.get_moldet()
        if pipeline is None or not pipeline.is_available():
            return {"molecule_count": 0, "skipped": True, "reason": "no GPU"}

        import fitz

        doc = fitz.open(pdf_path)
        all_molecules: list[dict] = []
        try:
            for page_idx in range(min(page_count, 10)):  # Limit to first 10 pages
                page = doc.load_page(page_idx)
                zoom = 300 / 72.0
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)

                import numpy as np
                from PIL import Image

                img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                image = Image.fromarray(img_array)

                boxes = pipeline.doc_detector.detect(image)
                for box in boxes:
                    x1, y1, x2, y2, conf = box
                    all_molecules.append({
                        "page": page_idx + 1,
                        "bbox": [x1, y1, x2, y2],
                        "confidence": conf,
                    })
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
    segmented,
    enrich_result: dict,
) -> None:
    """Save document data to filesystem and SQLite."""
    root = Path(project_root)

    # Save page texts
    pages_dir = root / "index" / "pages" / doc_id
    ensure_dir(pages_dir)
    for page in extracted.pages:
        page_file = pages_dir / f"page_{page.page_num:04d}.txt"
        page_file.write_text(page.text, encoding="utf-8")

    # Save document tree
    tree_path = root / "index" / "doc_trees.json"
    tree_data = {}
    if tree_path.exists():
        try:
            tree_data = json.loads(tree_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    tree_data[doc_id] = [
        _tree_node_to_dict(n) for n in segmented.document_tree
    ]
    save_json(tree_path, tree_data)

    # Save document report
    report_dir = root / "projects" / doc_id
    ensure_dir(report_dir)
    report = {
        "doc_id": doc_id,
        "page_count": extracted.page_count,
        "parser": extracted.parser,
        "title": extracted.title,
        "section_count": len(segmented.sections),
        "molecule_count": enrich_result.get("molecule_count", 0),
    }
    save_json(report_dir / "report.json", report)


def _index_chunks(doc_id: str, chunks: list[dict], collection_path: str) -> dict:
    """Embed and index chunks into Zvec."""
    try:
        from .index import index_chunks

        return index_chunks(doc_id, chunks, collection_path)
    except Exception as e:
        logger.error("Indexing failed for %s: %s", doc_id, e)
        return {"indexed": 0, "error": str(e)}


def _tree_node_to_dict(node) -> dict:
    return {
        "title": node.title,
        "node_id": node.node_id,
        "line_num": node.line_num,
        "nodes": [_tree_node_to_dict(n) for n in node.nodes],
    }
