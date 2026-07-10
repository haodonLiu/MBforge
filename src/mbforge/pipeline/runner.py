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
import contextlib
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.database import DatabaseManager
from ..utils.config import load_global_config
from ..utils.helpers import ensure_dir, save_json
from ..utils.logger import get_logger
from .stage_result import PipelineErrorCode, StageResult

logger = get_logger("mbforge.pipeline.runner")

# Per-stage progress percentages surfaced via _emit when task_id is set.
STAGE_PCT: dict[str, int] = {
    "extract": 10,
    "density": 18,
    "rough_md": 22,
    "detect": 32,
    "insert_molecode": 40,
    "popo": 48,  # optional MinerU-Popo post-process
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
        except Exception as exc:  # noqa: BLE001 — surface the failure, never silently drop
            logger.warning("record_ingest_event failed: %s", exc)
            # Also push to the diagnostics ring buffer so the failure is
            # visible to the front-end diagnostics view, not just the log.
            try:
                from ..utils.logger import push_diagnostic
                push_diagnostic(
                    {
                        "level": "WARNING",
                        "message": f"record_ingest_event failed: {exc}",
                        "category": "pipeline.runner",
                        "error_code": "ingest_log_write_failed",
                    }
                )
            except Exception:  # pragma: no cover - never let diagnostics compound the failure
                pass

    def _emit(
        event: str,
        message: str = "",
        *,
        stage: str | None = None,
        **data: Any,
    ) -> None:
        if on_progress:
            on_progress(
                PipelineEvent(
                    stage=stage or "pipeline", event=event, message=message, data=data
                ),
            )
        logger.info("[%s] %s", event, message)
        _maybe_record(event, message, stage=stage, **data)

    def _emit_stage_result(result: StageResult) -> None:
        """Emit a pipeline event from a StageResult.

        Recoverable failures are surfaced as ``warning`` events so the front-end
        knows the pipeline is continuing; fatal failures use ``error``.
        """
        data: dict[str, Any] = dict(result.context)
        if result.error_code:
            data["error_code"] = result.error_code
        data["recoverable"] = result.recoverable
        event_name = "warning" if result.recoverable else result.status
        _emit(
            event_name,
            result.message,
            stage=result.stage,
            **data,
        )

    def _run_stage(
        stage: str,
        fn: Callable[[], Any],
        *,
        recoverable: bool = False,
        error_code: str = PipelineErrorCode.UNKNOWN_ERROR,
        error_message: str | None = None,
    ) -> StageResult:
        """Execute one pipeline stage and return a structured StageResult.

        Non-recoverable errors emit an ``error`` event and raise the exception
        so the caller can abort the pipeline. Recoverable errors emit a
        ``warning`` event and return a StageResult without raising.
        """
        try:
            fn()
            return StageResult(
                stage=stage,
                status="success",
                message="OK",
            )
        except Exception as exc:
            msg = error_message or f"{stage} failed: {exc}"
            context = {"exception_type": type(exc).__name__, "detail": str(exc)}
            result = StageResult(
                stage=stage,
                status="error",
                message=msg,
                error_code=error_code,
                recoverable=recoverable,
                context=context,
            )
            _emit_stage_result(result)
            if recoverable:
                logger.warning("%s (recoverable): %s", msg, exc)
                return result
            logger.error("%s (fatal): %s", msg, exc)
            raise

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

    # -- Stage 3d-0: optional MinerU-Popo post-processing --
    # 当 config popo.enabled=true 且 MinerU-Popo 已安装时，对 OCR 后的 markdown
    # 做章节层级/表格续接/图说关联增强。失败或未安装则跳过。
    try:
        _cfg = load_global_config()
        if (_cfg.popo or {}).get("enabled", False):
            from ..backends import popo as _popo

            if _popo.popo_installed():
                _emit("progress", "Running MinerU-Popo post-processing...", stage="popo")
                pre_md = Path(enriched_md_path).read_text(encoding="utf-8")
                post_md = _popo.popo_postprocess_markdown(pre_md)
                if post_md and post_md != pre_md:
                    Path(enriched_md_path).write_text(post_md, encoding="utf-8")
                    _emit("complete", "MinerU-Popo post-processing applied", stage="popo")
                else:
                    _emit("warning", "MinerU-Popo returned no change", stage="popo")
            else:
                _emit("warning", "popo.enabled=true but MinerU-Popo not installed", stage="popo")
    except Exception as popo_exc:  # noqa: BLE001 — popo is optional, never crash the pipeline
        logger.warning("MinerU-Popo step failed: %s", popo_exc)
        _emit("warning", f"MinerU-Popo step failed: {popo_exc}", stage="popo")

    # -- Stage 3d: LLM reorganization --
    _emit("progress", "Reorganizing text...", stage="reorganize")
    # 把重整后的 markdown 存到 storage/{doc_id}/reorganized.md（与原 PDF 同目录）
    # Paths go through ArtifactResolver so doc_id is validated against
    # _SAFE_DOC_ID_RE and any traversal attempt is rejected at the chokepoint.
    from ..core.artifact import ArtifactResolver

    resolver = ArtifactResolver(root)
    storage_dir = resolver.storage_dir(doc_id)
    ensure_dir(storage_dir)
    final_md_path = resolver.reorganized_md(doc_id)

    def _run_reorganize() -> None:
        if density.doc_kind != "text_only" or candidates:
            from .organizer import reorganize_with_llm

            llm_cfg = load_global_config().llm
            reorganize_model = getattr(llm_cfg, "reorganize_model", None) or llm_cfg.model
            reorganize_with_llm(enriched_md_path, str(final_md_path), model=reorganize_model)
        else:
            _emit(
                "complete",
                "Reorganization skipped (text_only, no molecules)",
                stage="reorganize",
            )
            import shutil

            shutil.copy2(enriched_md_path, str(final_md_path))

    _run_stage(
        "reorganize",
        _run_reorganize,
        recoverable=True,
        error_code=PipelineErrorCode.LLM_REORGANIZE_FAILED,
        error_message="LLM reorganization failed",
    )
    _emit("complete", "Text reorganized", stage="reorganize")

    # 把原始 PDF 复制到 storage/{doc_id}/source.pdf，方便前端直接预览/下载
    try:
        import shutil

        source_pdf = resolver.source_pdf(doc_id)
        if Path(pdf_path).resolve() != source_pdf.resolve():
            shutil.copy2(pdf_path, str(source_pdf))
    except Exception as pdf_copy_exc:
        # The pipeline can still proceed without source.pdf in the storage
        # dir (the original PDF is still in library_root), but the failure
        # is no longer hidden. Surface it as a warning + diagnostics event
        # so the front-end diagnostics view + logs both see it.
        logger.warning("Failed to copy source PDF: %s", pdf_copy_exc)
        _emit(
            "warning",
            f"Failed to copy source PDF: {pdf_copy_exc}",
            stage="reorganize",
        )

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
        _emit(
            "warning",
            f"PageIndex indexing skipped: {e}",
            stage="pageindex",
            error_code=PipelineErrorCode.OPENKB_INDEX_FAILED,
            recoverable=True,
            exception_type=type(e).__name__,
        )

    # -- Stage 4: Wiki compilation --
    if openkb_doc_id:
        _emit("progress", "Compiling wiki...", stage="wiki")
        doc_name = Path(pdf_path).stem
        try:
            asyncio.run(adapter.compile_wiki(doc_name, doc_id, extracted.page_count))
            _emit("complete", "Wiki compiled", stage="wiki")
        except Exception as e:
            logger.warning("Wiki compilation failed for %s: %s", doc_id, e)
            _emit(
                "warning",
                f"Wiki compilation skipped: {e}",
                stage="wiki",
                error_code=PipelineErrorCode.OPENKB_WIKI_FAILED,
                recoverable=True,
                exception_type=type(e).__name__,
            )
    elif density.doc_kind == "image_only":
        _emit(
            "warning",
            "Wiki compile skipped for image-only doc with failed indexing",
            stage="wiki",
        )

    # -- Stages 5+6: Persist molecules + register text links (single txn) --
    # Both stages share one cross-database transaction so a failure in
    # either rolls back the other — preventing orphan rows in molecules,
    # evidence, or text_molecule_links.
    _emit("progress", "Persisting molecules...", stage="persist_mols")

    def _register_links_in_txn(mol_conn: Any) -> None:
        if not candidates or not final_md_path:
            return
        from .organizer import register_molecules_from_text

        register_molecules_from_text(
            str(final_md_path), candidates, doc_id, str(root), conn=mol_conn,
        )

    _run_stage(
        "persist_mols",
        lambda: _persist_molecules(
            root,
            doc_id,
            molecule_stats,
            register_links=_register_links_in_txn,
        ),
        recoverable=False,
        error_code=PipelineErrorCode.PERSIST_MOLECULES_FAILED,
        error_message="Molecule persistence or link registration failed",
    )
    _emit("complete", f"Persisted {molecule_count} molecules", stage="persist_mols")
    _emit(
        "complete",
        f"Registered {len(candidates)} molecule links",
        stage="register_links",
    )

    # -- Stage 7: Persist document --
    _emit("progress", "Saving document...", stage="persist")
    _run_stage(
        "persist",
        lambda: _persist_document(root, doc_id, extracted, density, molecule_stats),
        recoverable=False,
        error_code=PipelineErrorCode.PERSIST_DOCUMENT_FAILED,
        error_message="Document persistence failed",
    )
    _emit("complete", "Document saved", stage="persist")

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
        return {
            "molecule_count": 0,
            "rejected_count": 0,
            "skipped": True,
            "reason": f"extraction_failed: {e}",
            "error_code": PipelineErrorCode.MOLDET_UNAVAILABLE,
            "candidates": [],
        }

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
            "error_code": PipelineErrorCode.MOLECULE_NORMALIZATION_FAILED,
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
    *,
    register_links: Callable[[Any], None] | None = None,
    final_md_path: str | Path | None = None,
    candidates: list[Any] | None = None,
) -> None:
    """Persist molecule candidates + (optionally) register text links.

    Both writes share one cross-database transaction so a failure in
    either stage rolls back the other. The register_links callback (if
    provided) is called with the shared ``mol_conn`` so it can run
    ``register_molecules_from_text(..., conn=mol_conn)`` inside the same
    transaction.
    """
    # If the caller is supplying register_links, the candidates list lives
    # outside molecule_stats (it was already extracted earlier in
    # run_pipeline). Fall back to molecule_stats when not.
    effective_candidates = (
        candidates if candidates is not None else molecule_stats.get("candidates", [])
    )
    if not effective_candidates and register_links is None:
        return
    from .persist_molecules import persist_molecule_candidates

    root = Path(project_root) if isinstance(project_root, str) else project_root
    db = DatabaseManager.get(str(root))
    # Run inside the cross-database transaction so a failure does not leave
    # orphan molecule rows, evidence rows, or text_molecule_links rows.
    with db.transaction() as (_kb_conn, mol_conn):
        if effective_candidates:
            persist_molecule_candidates(
                str(root), doc_id, effective_candidates, conn=mol_conn
            )
        if register_links is not None:
            register_links(mol_conn)


def _persist_document(
    project_root: str | Path,
    doc_id: str,
    extracted: Any,
    density: Any,  # DensityClassification
    molecule_stats: dict[str, Any],
) -> None:
    """Save page texts and report to filesystem.

    All paths are produced by :class:`ArtifactResolver` so ``doc_id`` is
    validated against the safe-id regex and a path-traversal attempt is
    rejected at the chokepoint (raises ``InvalidDocIdError`` /
    ``PathTraversalError`` instead of writing outside the storage root).

    Rollback: every file written to disk is recorded in ``written_files``.
    If any write fails, the function deletes all previously written files
    before re-raising — so the storage dir never contains partial artifacts
    from a failed pipeline run.
    """
    root = Path(project_root) if isinstance(project_root, str) else project_root
    from ..core.artifact import ArtifactResolver

    resolver = ArtifactResolver(root)
    written_files: list[Path] = []
    try:
        pages_dir = resolver.pages_dir(doc_id)
        ensure_dir(pages_dir)
        for page in extracted.pages:
            page_file = resolver.page_text(doc_id, page.page_num)
            page_file.write_text(page.text, encoding="utf-8")
            written_files.append(page_file)

        report_dir = resolver.storage_dir(doc_id)
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
            "molecule_pending_review_count": molecule_stats.get(
                "pending_review_count", 0
            ),
            "molecule_rejected_count": molecule_stats.get("rejected_count", 0),
            "molecule_sources": molecule_stats.get("sources", []),
            "kb_backend": "openkb",
        }
        report_path = resolver.report_json(doc_id)
        save_json(report_path, report)
        written_files.append(report_path)
    except Exception:
        # Roll back any files we already wrote so the storage dir doesn't
        # contain partial artifacts from a failed run. We log + remove;
        # the caller (run_pipeline) decides whether the exception is fatal.
        for path in written_files:
            try:
                path.unlink(missing_ok=True)
            except Exception as cleanup_exc:  # pragma: no cover - defensive
                logger.warning(
                    "Failed to remove partial artifact %s during rollback: %s",
                    path,
                    cleanup_exc,
                )
        raise
