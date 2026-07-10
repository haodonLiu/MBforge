"""Unit tests for molecule normalization and deduplication."""

from __future__ import annotations

from mbforge.parsers.molecule.extraction_result import ExtractionResult
from mbforge.pipeline.normalize import normalize_molecules


def test_normalize_deduplicates_equivalent_smiles() -> None:
    """CCO, OCC, and C-C-O should all canonicalize to the same molecule."""
    candidates = [
        ExtractionResult(esmiles="CCO", source="text", status="pending"),
        ExtractionResult(esmiles="OCC", source="text", status="pending"),
    ]

    normalized = normalize_molecules(candidates)
    assert len(normalized) == 1
    assert normalized[0].canonical_smiles == "CCO"
    assert set(normalized[0].sources) == {"text"}
    assert normalized[0].status == "pending"


def test_normalize_keeps_image_and_text_sources_separate() -> None:
    """Two different molecules should produce two NormalizedMolecule records."""
    candidates = [
        ExtractionResult(esmiles="CCO", source="text", status="pending"),
        ExtractionResult(esmiles="c1ccccc1", source="image", status="pending"),
    ]

    normalized = normalize_molecules(candidates)
    assert len(normalized) == 2
    canonicals = {m.canonical_smiles for m in normalized}
    assert canonicals == {"CCO", "c1ccccc1"}


def test_normalize_rejects_invalid_smiles() -> None:
    """Garbage strings that RDKit cannot parse become rejected records."""
    candidates = [
        ExtractionResult(esmiles="not_a_smiles", source="text", status="pending"),
    ]

    normalized = normalize_molecules(candidates)
    assert len(normalized) == 1
    assert normalized[0].status == "rejected"
    assert normalized[0].reject_reason == "invalid_smiles"


def test_normalize_rejects_low_quality_fragments() -> None:
    """Single characters or pure digits are rejected as low quality."""
    candidates = [
        ExtractionResult(esmiles="C", source="text", status="pending"),
        ExtractionResult(esmiles="12345", source="text", status="pending"),
    ]

    normalized = normalize_molecules(candidates)
    assert len(normalized) == 2
    assert all(m.status == "rejected" for m in normalized)
    assert all(m.reject_reason == "low_quality_smiles" for m in normalized)


def test_normalize_rejects_non_chemistry_elements() -> None:
    """Symbols like [Re] are almost always OCR errors and should be rejected."""
    candidates = [
        ExtractionResult(esmiles="[Re]C", source="image", status="pending"),
    ]

    normalized = normalize_molecules(candidates)
    assert len(normalized) == 1
    assert normalized[0].status == "rejected"
    assert normalized[0].reject_reason == "invalid_element"


def test_normalize_merges_detections_sorted_by_confidence() -> None:
    """Duplicate canonical SMILES merge detections, highest confidence first."""
    candidates = [
        ExtractionResult(
            esmiles="CCO", source="image", composite_conf=0.5, status="pending"
        ),
        ExtractionResult(
            esmiles="CCO", source="image", composite_conf=0.9, status="pending"
        ),
    ]

    normalized = normalize_molecules(candidates)
    assert len(normalized) == 1
    assert len(normalized[0].detections) == 2
    assert normalized[0].detections[0].confidence == 0.9
    assert normalized[0].detections[1].confidence == 0.5
