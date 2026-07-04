from pathlib import Path

from mbforge.parsers.molecule.extraction_result import ExtractionResult
from mbforge.pipeline.normalize import normalize_molecules


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
    results = [
        ExtractionResult(esmiles="CCO", source="image"),
        ExtractionResult(esmiles="CCO", source="text"),
    ]
    # Both are valid SMILES, so this is just a control; force one invalid by
    # using a string that is not a valid SMILES alongside the same valid string.
    results = [
        ExtractionResult(esmiles="CCO", source="image"),
        ExtractionResult(esmiles="not-a-smiles", source="text"),
    ]
    normalized = normalize_molecules(results)
    assert len(normalized) == 2
    assert any(n.status == "pending" for n in normalized)
    assert any(n.status == "rejected" for n in normalized)


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
