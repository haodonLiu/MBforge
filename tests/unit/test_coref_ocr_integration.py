"""Integration tests for the OCR path inside routers/coref.py.

Verifies that:
1. Label bboxes from FT detector are cropped, batched, and OCR'd.
2. The OCR text propagates into both FigureLabel.label_text and
   CorefPrediction.label_text.
3. If OCR returns empty for a crop, label_text falls back to
   "Label {i}" (frontend still gets a non-empty string).
4. If the OCR adapter is unavailable (e.g. rapidocr not installed),
   the bridge still works with synthetic label_text.
5. Crop coordinate math is correct (pixel-space, 10% padding, clamped).

The FT detector is also mocked (with MagicMock + the CorefBbox-like
shapes) so the test runs in <1s and doesn't depend on the model
weights or CUDA.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PIL import Image

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coref_bbox(x1: float, y1: float, x2: float, y2: float,
                     conf: float, category_id: int) -> MagicMock:
    """Build a MagicMock that mimics a CorefBbox (used by coref_alt)."""
    cb = MagicMock()
    cb.bbox = (x1, y1, x2, y2)
    cb.score = conf
    cb.category_id = category_id
    return cb


def _mock_ocr_engine_returning(texts: list[str]) -> MagicMock:
    """Build a RapidOCR engine mock that returns ``texts`` (one per call)."""
    call_count = [0]

    def _call(img, use_det=None, use_rec=None):
        idx = call_count[0]
        call_count[0] += 1
        if idx >= len(texts):
            return None
        out = MagicMock()
        out.txts = [texts[idx]]
        out.scores = [0.95]
        return out

    engine = MagicMock()
    engine.side_effect = _call
    return engine


def _make_rendered_page_with_labels(
    width: int = 800, height: int = 1200
) -> Image.Image:
    """A flat white image. FT detection is mocked so the image content
    is irrelevant; we just need valid PIL.Image dimensions for cropping."""
    return Image.new("RGB", (width, height), (255, 255, 255))


def _setup_mock_ocr(ocr_texts: list[str]) -> None:
    """Inject a mock RapidOCRCropAdapter that returns ``ocr_texts``."""
    from mbforge.backends.ocr.rapidocr_adapter import RapidOCRCropAdapter

    RapidOCRCropAdapter.reset()
    engine = _mock_ocr_engine_returning(ocr_texts)
    RapidOCRCropAdapter._instance = RapidOCRCropAdapter.__new__(
        RapidOCRCropAdapter
    )
    RapidOCRCropAdapter._instance._engine = engine
    RapidOCRCropAdapter._init_error = None


def _set_ocr_init_error(error: BaseException) -> None:
    """Simulate RapidOCRCropAdapter.instance() raising an error."""
    from mbforge.backends.ocr.rapidocr_adapter import RapidOCRCropAdapter

    RapidOCRCropAdapter.reset()
    RapidOCRCropAdapter._init_error = error


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_ocr_singleton():
    from mbforge.backends.ocr.rapidocr_adapter import RapidOCRCropAdapter
    RapidOCRCropAdapter.reset()
    yield
    RapidOCRCropAdapter.reset()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_ocr_text_propagates_to_label_text():
    """The OCR'd text for each label bbox is the label_text we return."""
    from mbforge.routers import coref

    # Two label bboxes at known positions, one molecule.
    coref_result = MagicMock()
    coref_result.bboxes = [
        # molecule
        _make_coref_bbox(0.1, 0.2, 0.3, 0.4, 0.9, category_id=1),
        # label 1 -> "Ia"
        _make_coref_bbox(0.5, 0.2, 0.55, 0.22, 0.8, category_id=3),
        # label 2 -> "(Ib)"
        _make_coref_bbox(0.6, 0.3, 0.66, 0.33, 0.7, category_id=3),
    ]
    # FT pairing: (mol_idx, idt_idx) -> (0, 1), (0, 2)
    coref_result.corefs = [(0, 1), (0, 2)]

    _setup_mock_ocr(["Ia", "(Ib)"])

    image = _make_rendered_page_with_labels()
    ocr_texts = coref._run_label_ocr(image, coref_result)

    assert ocr_texts == ["Ia", "(Ib)"]

    labels, predictions = coref._coref_to_kb_shapes(
        coref_result=coref_result,
        page=1,
        doc_id="doc1",
        ocr_texts=ocr_texts,
    )
    assert labels[0]["label_text"] == "Ia"
    assert labels[1]["label_text"] == "(Ib)"
    # Predictions inherit the same text.
    assert predictions[0]["label_text"] == "Ia"
    assert predictions[1]["label_text"] == "(Ib)"


def test_empty_ocr_falls_back_to_synthetic_label():
    """If OCR returns "" for a label, fall back to 'Label {i}'."""
    from mbforge.routers import coref

    coref_result = MagicMock()
    coref_result.bboxes = [
        _make_coref_bbox(0.1, 0.2, 0.3, 0.4, 0.9, category_id=1),
        _make_coref_bbox(0.5, 0.2, 0.55, 0.22, 0.8, category_id=3),
    ]
    coref_result.corefs = [(0, 1)]

    _setup_mock_ocr([""])  # OCR returns empty

    image = _make_rendered_page_with_labels()
    ocr_texts = coref._run_label_ocr(image, coref_result)
    assert ocr_texts == [""]

    labels, predictions = coref._coref_to_kb_shapes(
        coref_result=coref_result,
        page=1,
        doc_id="doc1",
        ocr_texts=ocr_texts,
    )
    # Empty OCR text -> synthetic "Label 1"
    assert labels[0]["label_text"] == "Label 1"
    assert predictions[0]["label_text"] == "Label 1"


def test_ocr_unavailable_falls_back_to_synthetic():
    """If RapidOCRCropAdapter.instance() raises, label_text is synthetic."""
    from mbforge.routers import coref

    _set_ocr_init_error(ImportError("simulated missing rapidocr"))

    coref_result = MagicMock()
    coref_result.bboxes = [
        _make_coref_bbox(0.1, 0.2, 0.3, 0.4, 0.9, category_id=1),
        _make_coref_bbox(0.5, 0.2, 0.55, 0.22, 0.8, category_id=3),
    ]
    coref_result.corefs = [(0, 1)]

    image = _make_rendered_page_with_labels()
    ocr_texts = coref._run_label_ocr(image, coref_result)
    # Adapter unavailable -> per-crop slot is "" (empty), N labels = N empties.
    # The synthetic fallback then kicks in inside _coref_to_kb_shapes.
    assert ocr_texts == [""]

    labels, predictions = coref._coref_to_kb_shapes(
        coref_result=coref_result,
        page=1,
        doc_id="doc1",
        ocr_texts=ocr_texts,
    )
    # Falls back to synthetic "Label 1"
    assert labels[0]["label_text"] == "Label 1"


def test_run_label_ocr_returns_empty_list_when_no_labels():
    """When there are no label bboxes (category_id == 3), no OCR is run."""
    from mbforge.routers import coref

    # Only a molecule, no labels.
    coref_result = MagicMock()
    coref_result.bboxes = [
        _make_coref_bbox(0.1, 0.2, 0.3, 0.4, 0.9, category_id=1),
    ]
    coref_result.corefs = []

    # No mock needed - adapter should not be called.
    image = _make_rendered_page_with_labels()
    ocr_texts = coref._run_label_ocr(image, coref_result)
    assert ocr_texts == []

    labels, predictions = coref._coref_to_kb_shapes(
        coref_result=coref_result,
        page=1,
        doc_id="doc1",
        ocr_texts=ocr_texts,
    )
    assert labels == []
    assert predictions == []


def test_crop_label_boxes_pixel_coordinates():
    """Crops are computed in pixel coordinates, clamped to image bounds,
    with 10% padding on all sides."""
    from mbforge.routers import coref

    # bbox (0.5, 0.2, 0.55, 0.22) on 800x1200 -> pixel (400, 240, 440, 264)
    # bw=0.05, bh=0.02, padding=0.1 -> pad_w=0.005, pad_h=0.002 (normalized)
    # px1 = int((0.5 - 0.005) * 800)  = 396
    # py1 = int((0.2 - 0.002) * 1200) = 237
    # px2 = int((0.55 + 0.005) * 800) = 444
    # py2 = int((0.22 + 0.002) * 1200) = 266
    # size = (444 - 396, 266 - 237) = (48, 29)
    cb = _make_coref_bbox(0.5, 0.2, 0.55, 0.22, 0.8, category_id=3)
    image = _make_rendered_page_with_labels(800, 1200)
    crops = coref._crop_label_boxes(image, [cb])
    assert len(crops) == 1
    assert crops[0].size == (48, 29)


def test_crop_label_boxes_clamps_to_image_bounds():
    """Crops that extend past image edges get clamped, not negative."""
    from mbforge.routers import coref

    # bbox (0.0, 0.0, 0.1, 0.1) with 50% padding ->
    # pad_w = 0.05, pad_h = 0.05
    # Without clamp: (-0.05, -0.05, 0.15, 0.15)
    # After clamp: (0, 0, 120, 180) for 800x1200
    cb = _make_coref_bbox(0.0, 0.0, 0.1, 0.1, 0.8, category_id=3)
    image = _make_rendered_page_with_labels(800, 1200)
    crops = coref._crop_label_boxes(image, [cb], padding=0.5)
    # Without clamp: bw=80, bh=120, pad_w=40, pad_h=60
    # Expected: (max(0, 0-40)=0, max(0, 0-60)=0,
    #           min(800, 0+40+80)=120, min(1200, 0+60+120)=180)
    assert crops[0].size == (120, 180)


def test_ocr_batch_failure_returns_empty_strings():
    """If the batch OCR raises entirely, all labels get empty strings
    (and fall back to synthetic in _coref_to_kb_shapes)."""
    from mbforge.backends.ocr.rapidocr_adapter import RapidOCRCropAdapter
    from mbforge.routers import coref

    RapidOCRCropAdapter.reset()
    engine = MagicMock()
    engine.side_effect = RuntimeError("ONNX init failed")
    RapidOCRCropAdapter._instance = RapidOCRCropAdapter.__new__(
        RapidOCRCropAdapter
    )
    RapidOCRCropAdapter._instance._engine = engine
    RapidOCRCropAdapter._init_error = None

    coref_result = MagicMock()
    coref_result.bboxes = [
        _make_coref_bbox(0.1, 0.2, 0.3, 0.4, 0.9, category_id=1),
        _make_coref_bbox(0.5, 0.2, 0.55, 0.22, 0.8, category_id=3),
        _make_coref_bbox(0.6, 0.3, 0.66, 0.33, 0.7, category_id=3),
    ]
    coref_result.corefs = [(0, 1), (0, 2)]

    image = _make_rendered_page_with_labels()
    ocr_texts = coref._run_label_ocr(image, coref_result)
    # 2 labels -> 2 empty strings (caller falls back to synthetic).
    assert ocr_texts == ["", ""]

    labels, _ = coref._coref_to_kb_shapes(
        coref_result=coref_result,
        page=1,
        doc_id="doc1",
        ocr_texts=ocr_texts,
    )
    # Both labels fall back to synthetic.
    assert labels[0]["label_text"] == "Label 1"
    assert labels[1]["label_text"] == "Label 2"
