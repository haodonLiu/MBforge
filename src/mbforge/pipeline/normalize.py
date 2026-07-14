"""Normalize and deduplicate extracted molecule candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from rdkit import Chem

from ..parsers.molecule.extraction_result import ExtractionResult
from ..utils.logger import get_logger

logger = get_logger("mbforge.pipeline.normalize")

# Default set of allowed chemical elements for normalized molecules.
#
# This whitelist intentionally excludes most metals and heavy/main-group elements
# because the current pipeline (MolScribe + knowledge base) is tuned for small
# organic / drug-like molecules. Organometallic or inorganic structures that
# contain Re, Rf, Pb, Hg, etc. are rejected rather than silently imported with
# likely misread R-group labels. Callers can override this behavior by passing
# a custom ``allowed_elements`` set to :func:`normalize_molecules`.
DEFAULT_ALLOWED_ELEMENTS = {
    "C", "N", "O", "S", "F", "Cl", "Br", "I", "P", "B",
    "Si", "Se", "As", "H", "*",
}


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
        confidence=r.composite_conf,
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
    *,
    allowed_elements: set[str] | None = None,
) -> list[NormalizedMolecule]:
    """Validate SMILES, canonicalize, and deduplicate candidates.

    Valid molecules are keyed by canonical SMILES; invalid molecules are keyed
    by their raw extracted string so the two key spaces never collide.

    Args:
        results: Extraction results from MolScribe / text extraction.
        allowed_elements: Optional override for the element whitelist. When
            ``None``, :data:`DEFAULT_ALLOWED_ELEMENTS` is used. Pass a broader
            set (e.g. including ``"Fe"``, ``"Pt"``) to accept organometallic
            or inorganic structures.
    """
    by_canonical: dict[str, NormalizedMolecule] = {}
    by_invalid: dict[str, NormalizedMolecule] = {}

    # Pre-filter only for clearly unusable fragments. We do NOT reject SMILES
    # containing ``*`` here — ``*`` is a valid Markush wildcard atom (used by
    # patent R-group definitions) and is exactly what MolScribe emits for
    # markush structures. RDKit can parse and round-trip Markush SMILES, so
    # let it be the authoritative gate.
    def _is_unusable_fragment(esmiles: str) -> bool:
        if not esmiles or len(esmiles) < 3:
            return True
        # pure numeric (no atoms at all) — clearly garbage
        return bool(esmiles.isdigit())

    for r in results:
        if _is_unusable_fragment(r.esmiles):
            logger.debug("Rejected low-quality SMILES: %s", r.esmiles)
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
                    reject_reason="low_quality_smiles",
                    properties=properties,
                )
            continue

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

        # Element whitelist — RDKit accepts some rare elements that have
        # no place in a chemistry knowledge base (e.g. ``[Re]`` for Rhenium,
        # ``[Rf]`` for Rutherfordium). These are almost always MolScribe
        # mis-reading R-group subscripts (Rₑ / R_f). Treat as garbage.
        # The whitelist is configurable via ``allowed_elements`` so callers
        # can opt-in to organometallic/inorganic structures.
        allowed = allowed_elements if allowed_elements is not None else DEFAULT_ALLOWED_ELEMENTS
        invalid_atoms = [a.GetSymbol() for a in mol.GetAtoms()
                         if a.GetSymbol() not in allowed]
        if invalid_atoms:
            logger.debug(
                "Rejected SMILES with non-chemistry elements %s: %s",
                invalid_atoms, r.esmiles,
            )
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
                    reject_reason="invalid_element",
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
