from pathlib import Path
from unittest.mock import patch

from rdkit import Chem

from mbforge.parsers.molecule.extraction_result import ExtractionResult
from mbforge.pipeline.normalize import normalize_molecules

_REAL_MOL_FROM_SMILES = Chem.MolFromSmiles
_REAL_MOL_TO_SMILES = Chem.MolToSmiles


def test_normalize_rejects_invalid_smiles() -> None:
    results = [ExtractionResult(esmiles="not-a-smiles", source="text")]
    normalized = normalize_molecules(results)
    assert len(normalized) == 1
    assert normalized[0].status == "rejected"
    assert normalized[0].reject_reason == "invalid_smiles"


def test_normalize_deduplicates_same_smiles() -> None:
    results = [
        ExtractionResult(esmiles="CCO", source="image"),
        ExtractionResult(esmiles="CCO", source="text"),
    ]
    normalized = normalize_molecules(results)
    assert len(normalized) == 1
    assert normalized[0].canonical_smiles == "CCO"
    assert normalized[0].esmiles == "CCO"
    assert len(normalized[0].detections) == 2


def test_normalize_keeps_different_smiles() -> None:
    results = [
        ExtractionResult(esmiles="CCO", source="image"),
        ExtractionResult(esmiles="CCC", source="image"),
    ]
    normalized = normalize_molecules(results)
    assert len(normalized) == 2


def test_normalize_empty_input() -> None:
    assert normalize_molecules([]) == []


def test_normalize_multiple_invalid_smiles_remain_distinct() -> None:
    results = [
        ExtractionResult(esmiles="not-a-smiles", source="text"),
        ExtractionResult(esmiles="also-not-a-smiles", source="text"),
    ]
    normalized = normalize_molecules(results)
    assert len(normalized) == 2
    assert all(n.status == "rejected" for n in normalized)


def test_normalize_preserves_context_texts() -> None:
    results = [
        ExtractionResult(esmiles="CCO", source="image", context_text="caption A"),
        ExtractionResult(esmiles="CCO", source="text", context_text="paragraph B"),
    ]
    normalized = normalize_molecules(results)
    assert len(normalized) == 1
    assert normalized[0].properties["context_texts"] == ["caption A", "paragraph B"]


def test_normalize_collects_sources() -> None:
    results = [
        ExtractionResult(esmiles="CCO", source="image"),
        ExtractionResult(esmiles="CCO", source="text"),
    ]
    normalized = normalize_molecules(results)
    assert len(normalized) == 1
    assert "image" in normalized[0].sources
    assert "text" in normalized[0].sources
    assert len(normalized[0].sources) == 2


def test_normalize_image_path_string() -> None:
    img_path = Path("/tmp/mol.png")
    results = [
        ExtractionResult(
            esmiles="CCO",
            source="image",
            mol_img_path=img_path,
        ),
    ]
    normalized = normalize_molecules(results)
    assert len(normalized) == 1
    assert normalized[0].detections[0].image_path == str(img_path)
    assert isinstance(normalized[0].detections[0].image_path, str)


def test_normalize_detections_sorted_by_confidence() -> None:
    results = [
        ExtractionResult(esmiles="CCO", source="text", composite_conf=0.5),
        ExtractionResult(esmiles="CCO", source="image", composite_conf=0.9),
        ExtractionResult(esmiles="CCO", source="manual", composite_conf=0.7),
    ]
    normalized = normalize_molecules(results)
    assert len(normalized) == 1
    confidences = [d.confidence for d in normalized[0].detections]
    assert confidences == [0.9, 0.7, 0.5]


def test_normalize_zero_confidence_preserved() -> None:
    results = [
        ExtractionResult(esmiles="CCO", source="text", composite_conf=0.0),
        ExtractionResult(esmiles="CCO", source="image", composite_conf=0.9),
    ]
    normalized = normalize_molecules(results)
    assert len(normalized) == 1
    confidences = [d.confidence for d in normalized[0].detections]
    assert confidences == [0.9, 0.0]


def test_normalize_mixed_valid_and_invalid() -> None:
    results = [
        ExtractionResult(esmiles="CCO", source="image"),
        ExtractionResult(esmiles="not-a-smiles", source="text"),
    ]
    normalized = normalize_molecules(results)
    assert len(normalized) == 2
    statuses = {n.status for n in normalized}
    assert statuses == {"pending", "rejected"}


def test_normalize_valid_invalid_same_string_do_not_collide() -> None:
    """Same raw string can yield both a rejected invalid record and a valid one."""
    call_count = 0

    def _mol_from_smiles(smiles: str):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return None
        return _REAL_MOL_FROM_SMILES("CCO")

    with patch(
        "mbforge.pipeline.normalize.Chem.MolFromSmiles", side_effect=_mol_from_smiles
    ):
        results = [
            ExtractionResult(esmiles="CCO", source="image"),
            ExtractionResult(esmiles="CCO", source="text"),
        ]
        normalized = normalize_molecules(results)
        assert len(normalized) == 2
        assert call_count == 2

        rejected = next(n for n in normalized if n.status == "rejected")
        assert rejected.canonical_smiles == "CCO"
        assert rejected.reject_reason == "invalid_smiles"

        expected_canonical = _REAL_MOL_TO_SMILES(
            _REAL_MOL_FROM_SMILES("CCO"), canonical=True
        )
        pending = next(n for n in normalized if n.status == "pending")
        assert pending.canonical_smiles == expected_canonical


def test_normalize_duplicate_invalid_smiles_merge_detections() -> None:
    results = [
        ExtractionResult(esmiles="not-a-smiles", source="image", context_text="ctx A"),
        ExtractionResult(esmiles="not-a-smiles", source="text", context_text="ctx B"),
    ]
    normalized = normalize_molecules(results)
    assert len(normalized) == 1
    assert normalized[0].status == "rejected"
    assert normalized[0].reject_reason == "invalid_smiles"
    assert len(normalized[0].detections) == 2
    assert normalized[0].properties["context_texts"] == ["ctx A", "ctx B"]
    assert "image" in normalized[0].sources
    assert "text" in normalized[0].sources


def test_normalize_canonicalization_failure_rejected() -> None:
    """A result that parses but fails canonicalization is rejected and merges."""

    def _mol_to_smiles(*args, **kwargs):
        raise RuntimeError("forced canonicalization failure")

    with patch(
        "mbforge.pipeline.normalize.Chem.MolToSmiles", side_effect=_mol_to_smiles
    ):
        results = [
            ExtractionResult(esmiles="CCO", source="image"),
            ExtractionResult(esmiles="CCO", source="text"),
        ]
        normalized = normalize_molecules(results)
        assert len(normalized) == 1
        assert normalized[0].status == "rejected"
        assert normalized[0].reject_reason == "canonicalization_failed"
        assert len(normalized[0].detections) == 2
        assert "image" in normalized[0].sources
        assert "text" in normalized[0].sources
