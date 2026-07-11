"""Pipeline context — shared state across all stages.

Replaces function-local variables in the monolithic run_pipeline().
Each stage reads from and writes to this context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .classify import DensityClassification
    from .extract_text import ExtractedDocument

@dataclass
class PipelineContext:
    """Shared state container for pipeline execution.

    Attributes:
        pdf_path: Input PDF file path
        library_root: Library data directory (per-project root)
        doc_id: Document identifier
        task_id: Optional queue task ID for progress tracking
        ocr_config: OCR configuration dict

        extracted: ExtractedDocument from Stage 1
        density: DensityClassification from Stage 2
        rough_md_path: Temporary rough markdown path (Stage 3a)
        enriched_md_path: Markdown with MoleCode blocks (Stage 3c)
        final_md_path: LLM-reorganized markdown (Stage 3d)
        molecule_stats: Molecule extraction statistics
        candidates: List of NormalizedMolecule
        activity_records: List of ActivityRecord from Stage 3d-1
        openkb_doc_id: OpenKB document identifier
        indexed_count: Number of successfully indexed documents

        duration_ms: Total pipeline execution time
    """

    # ---- Inputs ----
    pdf_path: Path
    library_root: Path
    doc_id: str
    task_id: str | None = None
    ocr_config: dict = field(default_factory=dict)
    # ---- Stage 1: Extract ----
    extracted: ExtractedDocument | None = None

    # ---- Stage 2: Density ----
    density: DensityClassification | None = None

    # ---- Stage 3a-3c: Markdown + Molecules ----
    rough_md_path: Path | None = None
    enriched_md_path: Path | None = None
    final_md_path: Path | None = None
    molecule_stats: dict[str, Any] = field(default_factory=dict)
    candidates: list[Any] = field(default_factory=list)

    # ---- Stage 3d-1: Activities ----
    activity_records: list[Any] = field(default_factory=list)

    # ---- Stage 3e+4: Index + Wiki ----
    openkb_doc_id: str = ""
    indexed_count: int = 0

    # ---- Outputs ----
    duration_ms: int = 0
