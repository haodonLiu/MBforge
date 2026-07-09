"""Pipeline runner — orchestrates document processing via OpenKB + PageIndex.

Stages (9):
1. Extract: PDF text extraction (PyMuPDF + OCR fallback)
2. Density: Classify document as text_only / mixed / image_only
3a. Rough Markdown: Write page text to temporary .md file
3b. Detect: Molecule detection from PDF images (MolDet + MolScribe)
3c. MoleCode: Insert MoleCode blocks into markdown at bbox positions
3d. Reorganize: LLM-based semantic text reorganization
3e. PageIndex: Tree index via markdown parser (level-based, zero LLM)
4. Wiki: Compile summaries, concepts, entities
5. Persist Molecules: Write to molecules.db
6. Register Links: Extract molecule text context from reorganized text
7. Persist Document: Save page texts + report to filesystem
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.database import DatabaseManager
from ..utils.config import load_global_config
from ..utils.helpers import ensure_dir, save_json
from ..utils.logger import get_logger

logger = get_logger("mbforge.pipeline.runner")

# Per-stage progress percentages surfaced via _emit when task_id is set.
STAGE_PCT: dict[str, int] = {
    "extract": 10,
    "density": 18,
    "rough_md": 22,
    "detect": 32,
    "insert_molecode": 40,
    "reorganize": 55,
    "pageindex": 68,
    "wiki": 78,
    "persist_mols": 85,
    "register_links": 92,
    "persist": 100,
    "pipeline": 100,
}


def _current_ocr_config() -> dict:
    """Read current ocr config from AppConfig.ocr (settings.json)."""
    try:
        cfg = load_global_config()
        return dict(cfg.ocr or {})
    except Exception as exc:  # noqa: BLE001 — never block the pipeline on settings read failure
        logger.warning("Could not read OCR config: %s", exc)
        return {}


@dataclass
class PipelineEvent:
    stage: str
    event: str | None = None
    message: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class PipelineResult:
    doc_id: str
    page_count: int = 0
    indexed_count: int = 0
    parser: str = ""
    title: str = ""
    duration_ms: int = 0


ProgressCallback = Callable[[PipelineEvent], None]


def run_pipeline(
    pdf_path: str,
    library_root: str,
    doc_id: str = "",
    *,
    task_id: str | None = None,
    project_root: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> PipelineResult:
    """Run the document processing pipeline via OpenKB + PageIndex.

    Args:
        pdf_path: Path to the PDF file
        library_root: Library data directory
        doc_id: Document ID (auto-generated from filename if empty)
        task_id: Optional queue task ID. When set, stage progress is also
            written to ``ingest_queue`` (current_stage + progress_pct) and
            ``ingest_events`` via ``record_ingest_event``.
        project_root: Deprecated, use library_root
        on_progress: Progress callback

    Returns:
        PipelineResult with processing statistics
    """
    root = (
        Path(library_root or project_root)
        if library_root or project_root
        else Path(".")
    )
    if not doc_id:
        doc_id = Path(pdf_path).stem
    effective_task_id = task_id

    start_time = time.monotonic()

    def _maybe_record(
        event: str,
        message: str,
        *,
        stage: str | None = None,
        **data: Any,
    ) -> None:
        """Forward an _emit call to record_ingest_event when DB writes enabled.
        Imports lazily so the module loads even when the function isn't available.
        """
        if effective_task_id is None:
            return
        try:
            from ..core.database import record_ingest_event

            progress_pct: int | None = STAGE_PCT.get(stage) if stage else None
            status: str | None = "processing" if event == "start" else None
            record_ingest_event(
                DatabaseManager.get(str(root)),
                task_id=effective_task_id,
                doc_id=doc_id or None,
                stage=stage or "pipeline",
                level=event,
                message=message,
                data=data or None,
                progress_pct=progress_pct,
                status=status,
            )
        except Exception as exc:  # noqa: BLE001 — never let DB writes crash the pipeline
            logger.debug("record_ingest_event skipped: %s", exc)

    def _emit(
        event: str, message: str = "", *, stage: str | None = None, **data: Any
    ) -> None:
        if on_progress:
            on_progress(
                PipelineEvent(
                    stage=stage or "pipeline", event=event, message=message, data=data
                ),
            )
        logger.info("[%s] %s", event, message)
        _maybe_record(event, message, stage=stage, **data)

    _emit("start", f"Processing {Path(pdf_path).name}")

    # -- Stage 1: Extract text (with OCR) --
    _emit("progress", "Extracting text...", stage="extract")
    from .extract_text import extract_pdf_text

    extracted = extract_pdf_text(pdf_path, ocr_config=_current_ocr_config())
    _emit(
        "complete",
        f"Extracted {extracted.page_count} pages ({len(extracted.raw_text)} chars)",
        stage="extract",
    )

    # -- Stage 2: Density classification --
    from .classify import classify_density

    _emit("progress", "Classifying density...", stage="density")
    density = classify_density(extracted.pages)
    _emit(
        "complete",
        f"Density: {density.doc_kind} ({density.pages_needing_ocr}/{density.page_count} OCR)",
        stage="density",
        doc_kind=density.doc_kind,
        avg_text_density=density.avg_text_density,
    )

    # -- Stage 3a: Write rough markdown --
    _emit("progress", "Writing rough markdown...", stage="rough_md")
    import tempfile

    from .extract_text import write_rough_markdown

    rough_md_path = tempfile.mktemp(suffix=".md")
    write_rough_markdown(extracted.pages, rough_md_path)
    _emit(
        "complete",
        f"Rough markdown written: {Path(rough_md_path).name}",
        stage="rough_md",
    )

    # -- Stage 3b: Molecule detection (moved up from enrich) --
    _emit("progress", "Detecting molecules...", stage="detect")
    molecule_stats = _enrich_molecules(pdf_path, root, doc_id, density)
    molecule_count = molecule_stats.get("molecule_count", 0)
    if molecule_stats.get("skipped"):
        _emit(
            "warning",
            f"Molecule extraction skipped: {molecule_stats.get('reason', 'unknown')}",
            stage="detect",
        )
    else:
        _emit(
            "complete",
            f"Detected {molecule_count} molecules",
            stage="detect",
            molecule_count=molecule_count,
            rejected_count=molecule_stats.get("rejected_count", 0),
            pending_review_count=molecule_stats.get("pending_review_count", 0),
        )

    # -- Stage 3c: Insert MoleCode blocks --
    _emit("progress", "Inserting MoleCode blocks...", stage="insert_molecode")
    candidates = molecule_stats.get("candidates", [])
    enriched_md_path = tempfile.mktemp(suffix=".md")
    if candidates:
        from .organizer import insert_molecode_blocks

        insert_molecode_blocks(
            rough_md_path, extracted.pages, candidates, enriched_md_path
        )
    else:
        # No molecules to insert — copy rough md as-is
        import shutil

        shutil.copy2(rough_md_path, enriched_md_path)
    _emit(
        "complete",
        f"MoleCode blocks inserted: {len(candidates)} molecules",
        stage="insert_molecode",
    )

    # -- Stage 3d: LLM reorganization --
    _emit("progress", "Reorganizing text...", stage="reorganize")
    # 把重整后的 markdown 存到 storage/{doc_id}/reorganized.md（与原 PDF 同目录）
    storage_dir = root / "storage" / doc_id
    ensure_dir(storage_dir)
    final_md_path = storage_dir / "reorganized.md"
    if density.doc_kind != "text_only" or candidates:
        from .organizer import reorganize_with_llm

        llm_cfg = load_global_config().llm
        reorganize_model = getattr(llm_cfg, "reorganize_model", None) or llm_cfg.model
        reorganize_with_llm(enriched_md_path, str(final_md_path), model=reorganize_model)
    else:
        # text_only doc without molecules: reorganize maybe skipped
        _emit(
            "complete",
            "Reorganization skipped (text_only, no molecules)",
            stage="reorganize",
        )
        import shutil

        shutil.copy2(enriched_md_path, str(final_md_path))
    _emit("complete", "Text reorganized", stage="reorganize")

    # 把原始 PDF 复制到 storage/{doc_id}/source.pdf，方便前端直接预览/下载
    try:
        import shutil

        source_pdf = storage_dir / "source.pdf"
        if Path(pdf_path).resolve() != source_pdf.resolve():
            shutil.copy2(pdf_path, str(source_pdf))
    except Exception as pdf_copy_exc:
        logger.debug("Failed to copy source PDF: %s", pdf_copy_exc)

    # -- Stage 3e: PageIndex tree indexing via markdown --
    _emit("progress", "Building PageIndex tree...", stage="pageindex")
    from ..openkb.adapter import OpenKBAdapter

    adapter = OpenKBAdapter(root)
    openkb_doc_id = ""
    indexed_count = 0
    try:
        openkb_doc_id = adapter.index_markdown(final_md_path, doc_id)
        indexed_count = 1
        _emit("complete", f"PageIndex tree built: {openkb_doc_id}", stage="pageindex")
    except Exception as e:
        logger.warning("PageIndex indexing failed for %s: %s", pdf_path, e)
        _emit("warning", f"PageIndex indexing skipped: {e}", stage="pageindex")

    # -- Stage 4: Wiki compilation --
    if openkb_doc_id:
        _emit("progress", "Compiling wiki...", stage="wiki")
        doc_name = Path(pdf_path).stem
        try:
            asyncio.run(adapter.compile_wiki(doc_name, doc_id, extracted.page_count))
            _emit("complete", "Wiki compiled", stage="wiki")
        except Exception as e:
            logger.warning("Wiki compilation failed for %s: %s", doc_id, e)
            _emit("warning", f"Wiki compilation skipped: {e}", stage="wiki")
    elif density.doc_kind == "image_only":
        _emit(
            "warning",
            "Wiki compile skipped for image-only doc with failed indexing",
            stage="wiki",
        )

    # -- Stage 5: Persist molecules --
    _emit("progress", "Persisting molecules...", stage="persist_mols")
    _persist_molecules(root, doc_id, molecule_stats)
    _emit("complete", f"Persisted {molecule_count} molecules", stage="persist_mols")

    # -- Stage 6: Register molecule links from reorganized text --
    _emit("progress", "Registering molecule links...", stage="register_links")
    if candidates:
        from .organizer import register_molecules_from_text

        register_molecules_from_text(final_md_path, candidates, doc_id, str(root))
    _emit(
        "complete",
        f"Registered {len(candidates)} molecule links",
        stage="register_links",
    )

    # -- Stage 7: Persist document --
    _emit("progress", "Saving document...", stage="persist")
    _persist_document(root, doc_id, extracted, density, molecule_stats)
    _emit("complete", "Document saved", stage="persist")

    import contextlib

    for p in [rough_md_path, enriched_md_path]:
        with contextlib.suppress(Exception):
            Path(p).unlink(missing_ok=True)
    # final_md_path 已落到 storage/{doc_id}/reorganized.md，不再清理

    duration_ms = int((time.monotonic() - start_time) * 1000)
    _emit("complete", f"Pipeline finished in {duration_ms}ms", stage="pipeline")

    return PipelineResult(
        doc_id=doc_id,
        page_count=extracted.page_count,
        indexed_count=indexed_count,
        parser=extracted.parser,
        title=extracted.title,
        duration_ms=duration_ms,
    )


def _enrich_molecules(
    pdf_path: str,
    project_root: str | Path,
    doc_id: str,
    density: Any,  # DensityClassification
) -> dict[str, Any]:
    """Extract molecules from PDF images, normalize, return candidates (not persisted).

    Args:
        density: DensityClassification — used to skip molecule extraction
            for text_only documents (no figures expected).
    """
    from .extract_molecules import extract_molecules_from_pdf
    from .normalize import normalize_molecules

    root = Path(project_root) if isinstance(project_root, str) else project_root

    # text_only docs: no figures expected, skip entirely
    if density.doc_kind == "text_only":
        return {
            "molecule_count": 0,
            "rejected_count": 0,
            "skipped": True,
            "reason": "text_only",
            "candidates": [],
        }

    try:
        image_results = extract_molecules_from_pdf(pdf_path, str(root), doc_id)
    except Exception as e:
        logger.warning("Molecule image extraction failed: %s", e)
        image_results = []

    if not image_results:
        return {
            "molecule_count": 0,
            "rejected_count": 0,
            "skipped": True,
            "reason": "no candidates",
            "candidates": [],
        }

    try:
        normalized = normalize_molecules(image_results)
    except Exception as e:
        logger.warning("Molecule normalization failed: %s", e)
        return {
            "molecule_count": 0,
            "rejected_count": 0,
            "error": f"normalization failed: {e}",
            "candidates": [],
        }

    pending = [n for n in normalized if n.status == "pending"]
    pending_review = [n for n in normalized if n.status == "pending_review"]
    rejected = [n for n in normalized if n.status == "rejected"]
    sources: set[str] = set()
    for n in normalized:
        sources.update(n.sources)

    return {
        "molecule_count": len(pending) + len(pending_review),
        "rejected_count": len(rejected),
        "pending_review_count": len(pending_review),
        "total_candidates": len(normalized),
        "sources": sorted(sources),
        "candidates": normalized,
    }


def _persist_molecules(
    project_root: str | Path,
    doc_id: str,
    molecule_stats: dict[str, Any],
) -> None:
    """Persist molecule candidates produced by _enrich_molecules."""
    candidates = molecule_stats.get("candidates", [])
    if not candidates:
        return
    from .persist_molecules import persist_molecule_candidates

    root = Path(project_root) if isinstance(project_root, str) else project_root
    try:
        persist_molecule_candidates(str(root), doc_id, candidates)
    except Exception as e:
        logger.warning("Molecule persistence failed: %s", e)


def _persist_document(
    project_root: str | Path,
    doc_id: str,
    extracted: Any,
    density: Any,  # DensityClassification
    molecule_stats: dict[str, Any],
) -> None:
    """Save page texts and report to filesystem."""
    root = Path(project_root) if isinstance(project_root, str) else project_root

    pages_dir = root / "storage" / doc_id / "pages"
    ensure_dir(pages_dir)
    for page in extracted.pages:
        page_file = pages_dir / f"page_{page.page_num:04d}.txt"
        page_file.write_text(page.text, encoding="utf-8")

    report_dir = root / "storage" / doc_id
    ensure_dir(report_dir)
    report = {
        "doc_id": doc_id,
        "page_count": extracted.page_count,
        "parser": extracted.parser,
        "title": extracted.title,
        "doc_kind": density.doc_kind,
        "avg_text_density": density.avg_text_density,
        "pages_needing_ocr": density.pages_needing_ocr,
        "molecule_count": molecule_stats.get("molecule_count", 0),
        "molecule_pending_review_count": molecule_stats.get("pending_review_count", 0),
        "molecule_rejected_count": molecule_stats.get("rejected_count", 0),
        "molecule_sources": molecule_stats.get("sources", []),
        "kb_backend": "openkb",
    }
    save_json(report_dir / "report.json", report)
