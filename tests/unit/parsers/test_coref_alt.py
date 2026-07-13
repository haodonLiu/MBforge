from __future__ import annotations

from unittest.mock import patch

from PIL import Image

from mbforge.backends.moldet_v2_ft import MolDetv2FTDetector
from mbforge.parsers.molecule.coref_alt import (
    CorefBbox,
    CorefResult,
    _ocr_identifier_crops,
    detect_coref_via_ft_detector,
)


class _FakeFTDetector(MolDetv2FTDetector):
    """Minimal stand-in for ``MolDetv2FTDetector`` that returns fixed boxes."""

    def __init__(self, boxes: list[tuple[float, float, float, float, float, int]]):
        # Intentionally skip MolDetv2FTDetector.__init__ to avoid model loading.
        self._boxes = boxes

    def is_available(self) -> bool:
        return True

    def detect(self, image):  # noqa: ARG002 - matches detector API
        return self._boxes


def test_ocr_identifier_crops_returns_empty_on_adapter_failure() -> None:
    """If RapidOCRCropAdapter fails to initialize, identifiers keep empty text."""
    image = Image.new("RGB", (100, 100), (255, 255, 255))
    bboxes = [
        CorefBbox(category_id=1, bbox=(0.2, 0.2, 0.4, 0.4), score=0.9),
        CorefBbox(category_id=3, bbox=(0.05, 0.05, 0.15, 0.15), score=0.8),
    ]
    idt_indices = [1]

    with patch(
        "mbforge.backends.ocr.rapidocr_adapter.RapidOCRCropAdapter.instance"
    ) as mock_instance:
        mock_instance.side_effect = RuntimeError("ONNX not found")
        texts = _ocr_identifier_crops(image, idt_indices, bboxes)

    assert texts == [""]


def test_detect_coref_via_ft_detector_fills_identifier_text_from_ocr() -> None:
    """Identifier bboxes receive real text from RapidOCRCropAdapter."""
    image = Image.new("RGB", (100, 100), (255, 255, 255))
    detector = _FakeFTDetector(
        [
            (5, 5, 15, 15, 0.8, 3),   # identifier -> OCR "1a"
            (20, 20, 40, 40, 0.9, 1),  # molecule
        ]
    )

    with patch(
        "mbforge.backends.ocr.rapidocr_adapter.RapidOCRCropAdapter"
    ) as mock_adapter:
        mock_adapter.instance.return_value.readtext_batch.return_value = ["1a"]
        result = detect_coref_via_ft_detector(
            image, ft_detector=detector, use_ocr=True
        )

    assert isinstance(result, CorefResult)
    assert len(result.bboxes) == 2
    assert result.bboxes[0].category_id == 3
    assert result.bboxes[0].text == "1a"
    assert result.bboxes[1].category_id == 1
    assert result.corefs == [(1, 0)]


def test_detect_coref_via_ft_detector_skips_ocr_when_disabled() -> None:
    """With ``use_ocr=False`` identifier text stays empty."""
    image = Image.new("RGB", (100, 100), (255, 255, 255))
    detector = _FakeFTDetector(
        [
            (5, 5, 15, 15, 0.8, 3),
            (20, 20, 40, 40, 0.9, 1),
        ]
    )

    with patch(
        "mbforge.backends.ocr.rapidocr_adapter.RapidOCRCropAdapter"
    ) as mock_adapter:
        result = detect_coref_via_ft_detector(
            image, ft_detector=detector, use_ocr=False
        )

    assert result.bboxes[0].text == ""
    mock_adapter.instance.assert_not_called()
