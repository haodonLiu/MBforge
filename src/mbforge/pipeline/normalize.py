"""Normalize and deduplicate extracted molecule candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from rdkit import Chem

from ..parsers.molecule.extraction_result import ExtractionResult
from ..utils.logger import get_logger

logger = get_logger("mbforge.pipeline.normalize")


@dataclass
class DetectionSource:
    """One concrete detection of a molecule in a document.

    Attributes:
        source: Origin of the detection (image model, text regex, manual entry).
        page: Page index in the PDF (0-based), if known.
        bbox: Bounding box in PDF coordinates (left, bottom, right, top), if known.
        image_path: Path to the cropped molecule image for image detections.
        confidence: Detection confidence, normalized to [0, 1].
    """

    source: Literal["image", "text", "manual"]
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    image_path: str | None = None
    confidence: float = 0.0


@dataclass
class NormalizedMolecule:
    """Canonicalized molecule with all detections merged.

    Attributes:
        canonical_smiles: RDKit-canonical SMILES for valid molecules, or the raw
            input string for rejected/invalid records.
        esmiles: Original extracted SMILES string as produced by the upstream
            extractor (preserved for traceability).
        name: Compound name, if any was extracted.
        sources: Distinct detection sources (e.g., image and text).
        detections: All individual detections, sorted highest-confidence first.
        status: ``pending`` for valid molecules awaiting review, ``rejected``
            when the SMILES could not be parsed or canonicalized.
        reject_reason: Machine-readable reason when ``status`` is ``rejected``.
        properties: Additional merged metadata such as ``context_texts``.
    """

    canonical_smiles: str
    esmiles: str
    name: str
    sources: list[Literal["image", "text", "manual"]] = field(default_factory=list)
    detections: list[DetectionSource] = field(default_factory=list)
    status: Literal["pending", "rejected"] = "pending"
    reject_reason: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


def _detection_from_result(r: ExtractionResult) -> DetectionSource:
    """Build a DetectionSource from an ExtractionResult."""
    return DetectionSource(
        source=r.source,
        page=r.page_idx,
        bbox=r.bbox_pdf,
        image_path=str(r.mol_img_path) if r.mol_img_path else None,
        confidence=r.composite_conf or r.moldet_conf or r.scribe_conf,
    )


def _append_context(properties: dict[str, Any], context_text: str) -> None:
    """Accumulate non-empty context texts in a list."""
    if not context_text:
        return
    contexts: list[str] = properties.setdefault("context_texts", [])
    contexts.append(context_text)


def _add_source(
    sources: list[Literal["image", "text", "manual"]],
    source: Literal["image", "text", "manual"],
) -> None:
    """Append a source if it is not already tracked."""
    if source not in sources:
        sources.append(source)


def _merge_detection(existing: NormalizedMolecule, r: ExtractionResult) -> None:
    """Append a detection to an existing molecule and keep it sorted."""
    existing.detections.append(_detection_from_result(r))
    existing.detections.sort(key=lambda d: d.confidence, reverse=True)
    _add_source(existing.sources, r.source)
    _append_context(existing.properties, r.context_text)


def normalize_molecules(
    results: list[ExtractionResult],
) -> list[NormalizedMolecule]:
    """Validate SMILES, canonicalize, and deduplicate candidates.

    Valid molecules are keyed by canonical SMILES; invalid molecules are keyed
    by their raw extracted string so the two key spaces never collide.
    """
    by_canonical: dict[str, NormalizedMolecule] = {}
    by_invalid: dict[str, NormalizedMolecule] = {}

    for r in results:
        try:
            mol = Chem.MolFromSmiles(r.esmiles)
        except Exception as exc:
            logger.debug("RDKit error for %r: %s", r.esmiles, exc)
            mol = None

        if mol is None:
            logger.debug("Rejected invalid SMILES: %s", r.esmiles)
            if r.esmiles in by_invalid:
                _merge_detection(by_invalid[r.esmiles], r)
            else:
                properties: dict[str, Any] = {}
                _append_context(properties, r.context_text)
                by_invalid[r.esmiles] = NormalizedMolecule(
                    canonical_smiles=r.esmiles,
                    esmiles=r.esmiles,
                    name=r.name,
                    sources=[r.source],
                    detections=[_detection_from_result(r)],
                    status="rejected",
                    reject_reason="invalid_smiles",
                    properties=properties,
                )
            continue

        try:
            canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        except Exception as exc:
            logger.debug("RDKit canonicalization error for %r: %s", r.esmiles, exc)
            if r.esmiles in by_invalid:
                _merge_detection(by_invalid[r.esmiles], r)
            else:
                properties = {}
                _append_context(properties, r.context_text)
                by_invalid[r.esmiles] = NormalizedMolecule(
                    canonical_smiles=r.esmiles,
                    esmiles=r.esmiles,
                    name=r.name,
                    sources=[r.source],
                    detections=[_detection_from_result(r)],
                    status="rejected",
                    reject_reason="canonicalization_failed",
                    properties=properties,
                )
            continue

        if canonical in by_canonical:
            _merge_detection(by_canonical[canonical], r)
        else:
            properties = {}
            _append_context(properties, r.context_text)
            by_canonical[canonical] = NormalizedMolecule(
                canonical_smiles=canonical,
                esmiles=r.esmiles,
                name=r.name,
                sources=[r.source],
                detections=[_detection_from_result(r)],
                status="pending",
                properties=properties,
            )

    return list(by_canonical.values()) + list(by_invalid.values())
