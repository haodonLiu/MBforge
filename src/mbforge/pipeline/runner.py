"""Pipeline runner — orchestrates document processing via OpenKB + PageIndex.

Stages:
1. Extract: PDF text extraction (PyMuPDF + OCR fallback)
2. Classify: Patent / paper / report heuristic classification
3. PageIndex: Tree index via LLM reasoning
4. Wiki: Compile summaries, concepts, entities
5. Enrich: Molecule extraction from figures (MolDet + MolScribe) and text
   SMILES, normalized via RDKit and persisted to molecules.db
6. Persist: Save page texts + report to filesystem
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

    # Stage 2: Classify
    _emit("progress", "Classifying document...", stage="classify")
    from .classify import classify_document

    classification = classify_document(extracted.raw_text)
    _emit(
        "complete",
        f"Document type: {classification.doc_type} ({classification.confidence:.2f})",
        stage="classify",
        doc_type=classification.doc_type,
        confidence=classification.confidence,
    )

    # Stage 3: PageIndex tree indexing
    _emit("progress", "Building PageIndex tree...", stage="pageindex")
    from ..openkb.adapter import OpenKBAdapter

    adapter = OpenKBAdapter(project_root)
    openkb_doc_id = adapter.index_document(pdf_path, doc_id)
    _emit("complete", f"PageIndex tree built: {openkb_doc_id}", stage="pageindex")

    # Stage 4: Wiki compilation
    _emit("progress", "Compiling wiki...", stage="wiki")
    doc_name = Path(pdf_path).stem
    import asyncio

    asyncio.run(adapter.compile_wiki(doc_name, doc_id, extracted.page_count))
    _emit("complete", "Wiki compiled", stage="wiki")

    # Stage 5: Enrich (molecule extraction + normalization + persist)
    _emit("progress", "Detecting molecules...", stage="enrich")
    molecule_stats = _enrich_and_persist_molecules(
        pdf_path, project_root, doc_id, extracted.raw_text
    )
    _emit(
        "complete",
        f"Detected {molecule_stats.get('molecule_count', 0)} molecules",
        stage="enrich",
        molecule_count=molecule_stats.get("molecule_count", 0),
        rejected_count=molecule_stats.get("rejected_count", 0),
    )

    # Stage 6: Persist
    _emit("progress", "Saving document...", stage="persist")
    _persist_document(project_root, doc_id, extracted, classification, molecule_stats)
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


def _enrich_and_persist_molecules(
    pdf_path: str,
    project_root: str,
    doc_id: str,
    raw_text: str,
) -> dict[str, Any]:
    """Extract molecules from PDF images and text, normalize, and persist.

    Errors are logged and swallowed so that molecule extraction never aborts
    the rest of the pipeline.
    """
    from .extract_molecules import (
        extract_molecules_from_pdf,
        extract_molecules_from_text,
    )
    from .normalize import normalize_molecules
    from .persist_molecules import persist_molecule_candidates

    try:
        image_results = extract_molecules_from_pdf(pdf_path, project_root, doc_id)
    except Exception as e:
        logger.warning("Molecule image extraction failed: %s", e)
        image_results = []

    try:
        text_results = extract_molecules_from_text(raw_text, doc_id)
    except Exception as e:
        logger.warning("Molecule text extraction failed: %s", e)
        text_results = []

    combined = image_results + text_results
    if not combined:
        return {
            "molecule_count": 0,
            "rejected_count": 0,
            "skipped": True,
            "reason": "no candidates",
        }

    try:
        normalized = normalize_molecules(combined)
    except Exception as e:
        logger.warning("Molecule normalization failed: %s", e)
        return {
            "molecule_count": 0,
            "rejected_count": 0,
            "error": f"normalization failed: {e}",
        }

    try:
        persist_molecule_candidates(project_root, doc_id, normalized)
    except Exception as e:
        logger.warning("Molecule persistence failed: %s", e)
        return {
            "molecule_count": 0,
            "rejected_count": 0,
            "error": f"persistence failed: {e}",
        }

    pending = [n for n in normalized if n.status == "pending"]
    rejected = [n for n in normalized if n.status == "rejected"]
    sources: set[str] = set()
    for n in normalized:
        sources.update(n.sources)

    return {
        "molecule_count": len(pending),
        "rejected_count": len(rejected),
        "total_candidates": len(combined),
        "sources": sorted(sources),
    }


def _persist_document(
    project_root: str,
    doc_id: str,
    extracted,
    classification,
    molecule_stats: dict[str, Any],
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
        "doc_type": classification.doc_type,
        "doc_type_confidence": classification.confidence,
        "molecule_count": molecule_stats.get("molecule_count", 0),
        "molecule_rejected_count": molecule_stats.get("rejected_count", 0),
        "molecule_sources": molecule_stats.get("sources", []),
        "kb_backend": "openkb",
    }
    save_json(report_dir / "report.json", report)
