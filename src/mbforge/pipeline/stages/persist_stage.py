"""Stage 5-7: Persist Molecules + Register Links + Persist Document.

Combines three persist steps into one stage with unified transaction.
"""

from __future__ import annotations

from typing import Any

from ...core.artifact import ArtifactResolver
from ...core.database import DatabaseManager
from ...utils.helpers import ensure_dir, save_json
from ...utils.logger import get_logger
from ..context import PipelineContext
from ..stage_result import PipelineErrorCode, StageResult

logger = get_logger("mbforge.pipeline.stages.persist")


class PersistStage:
    """Stage 5-7: Persist molecules + text links + document (single txn)."""

    def execute(self, ctx: PipelineContext) -> StageResult:
        """Persist all data to database + filesystem.

        Reads:
            ctx.candidates: list[NormalizedMolecule]
            ctx.activity_records: list[ActivityRecord]
            ctx.final_md_path: Path
            ctx.extracted: ExtractedDocument
            ctx.density: DensityClassification
            ctx.molecule_stats: dict

        Writes:
            Database: molecules, evidence, text_molecule_links
            Filesystem: storage/{doc_id}/pages/, report.json
        """
        # Stage 5+6: Persist molecules + register links (single txn)
        try:
            self._persist_molecules_and_links(ctx)
        except Exception as e:
            logger.error("Molecule persistence failed for %s: %s", ctx.doc_id, e)
            return StageResult(
                stage="persist",
                status="error",
                message=f"Molecule persistence failed: {e}",
                error_code=PipelineErrorCode.PERSIST_MOLECULES_FAILED,
                recoverable=False,
                context={"exception_type": type(e).__name__, "detail": str(e)},
            )

        # Stage 7: Persist document to filesystem
        try:
            self._persist_document(ctx)
        except Exception as e:
            logger.error("Document persistence failed for %s: %s", ctx.doc_id, e)
            return StageResult(
                stage="persist",
                status="error",
                message=f"Document persistence failed: {e}",
                error_code=PipelineErrorCode.PERSIST_DOCUMENT_FAILED,
                recoverable=False,
                context={"exception_type": type(e).__name__, "detail": str(e)},
            )

        molecule_count = ctx.molecule_stats.get("molecule_count", 0)
        return StageResult(
            stage="persist",
            status="success",
            message=f"Persisted {molecule_count} molecules + document",
            context={
                "molecule_count": molecule_count,
                "page_count": ctx.extracted.page_count,
            },
        )

    def _persist_molecules_and_links(self, ctx: PipelineContext) -> None:
        """Persist molecules + text links in single cross-database transaction."""
        if not ctx.candidates:
            logger.info("No molecules to persist for %s", ctx.doc_id)
            return

        from ..persist_molecules import persist_molecule_candidates

        db = DatabaseManager.get(str(ctx.library_root))

        def _register_links_in_txn(mol_conn: Any) -> None:
            """Register text links inside transaction."""
            if not ctx.candidates or not ctx.final_md_path:
                return
            from ..organizer import register_molecules_from_text

            register_molecules_from_text(
                str(ctx.final_md_path),
                ctx.candidates,
                ctx.doc_id,
                str(ctx.library_root),
                conn=mol_conn,
            )

        # Run inside cross-database transaction
        with db.transaction() as (_kb_conn, mol_conn):
            persist_molecule_candidates(
                str(ctx.library_root),
                ctx.doc_id,
                ctx.candidates,
                conn=mol_conn,
                activity_records=ctx.activity_records,
            )
            _register_links_in_txn(mol_conn)

        logger.info(
            "Persisted %d molecules + links for %s",
            len(ctx.candidates),
            ctx.doc_id,
        )

    def _persist_document(self, ctx: PipelineContext) -> None:
        """Save page texts and report to filesystem with rollback on failure."""
        resolver = ArtifactResolver(ctx.library_root)
        written_files: list[Any] = []

        try:
            # Write page texts
            pages_dir = resolver.pages_dir(ctx.doc_id)
            ensure_dir(pages_dir)
            for page in ctx.extracted.pages:
                page_file = resolver.page_text(ctx.doc_id, page.page_num)
                page_file.write_text(page.text, encoding="utf-8")
                written_files.append(page_file)

            # Write report.json
            report_dir = resolver.storage_dir(ctx.doc_id)
            ensure_dir(report_dir)
            report = {
                "doc_id": ctx.doc_id,
                "page_count": ctx.extracted.page_count,
                "parser": ctx.extracted.parser,
                "title": ctx.extracted.title,
                "doc_kind": ctx.density.doc_kind,
                "avg_text_density": ctx.density.avg_text_density,
                "pages_needing_ocr": ctx.density.pages_needing_ocr,
                "molecule_count": ctx.molecule_stats.get("molecule_count", 0),
                "molecule_pending_review_count": ctx.molecule_stats.get(
                    "pending_review_count", 0
                ),
                "molecule_rejected_count": ctx.molecule_stats.get("rejected_count", 0),
                "molecule_sources": ctx.molecule_stats.get("sources", []),
                "kb_backend": "openkb",
            }
            report_path = resolver.report_json(ctx.doc_id)
            save_json(report_path, report)
            written_files.append(report_path)

            logger.info("Document persisted for %s", ctx.doc_id)

        except Exception:
            # Roll back any files we already wrote
            for path in written_files:
                try:
                    path.unlink(missing_ok=True)
                except Exception as cleanup_exc:
                    logger.warning(
                        "Failed to remove partial artifact %s during rollback: %s",
                        path,
                        cleanup_exc,
                    )
            raise
