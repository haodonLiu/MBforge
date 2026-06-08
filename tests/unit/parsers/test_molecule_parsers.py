"""Molecule parser unit tests — coords, extraction result, image pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from mbforge.parsers.molecule.coords import (
    image_to_pdf_bbox,
    pdf_to_image_bbox,
    scale_from_page_size,
)
from mbforge.parsers.molecule.extraction_result import ExtractionResult
from mbforge.backends.moldet import (
    MolDetv2DocDetector,
    MolImagePipeline,
    MolScribeRecognizer,
)


# ============================================================================
# Coords
# ============================================================================

class TestScaleFromPageSize:
    def test_scale_basic(self):
        page_w_pts = 595.0
        page_h_pts = 842.0
        image_w = 2480
        image_h = 3508
        scale = scale_from_page_size(page_w_pts, page_h_pts, image_w, image_h)
        expected = image_w / page_w_pts
        assert abs(scale - expected) < 1e-6
        assert abs(scale - (image_h / page_h_pts)) < 0.1

    def test_scale_non_uniform(self):
        page_w_pts = 100.0
        page_h_pts = 100.0
        image_w = 200
        image_h = 250
        scale = scale_from_page_size(page_w_pts, page_h_pts, image_w, image_h)
        assert scale == 2.0


class TestImageToPdfBBox:
    def test_basic_conversion(self):
        page_h_pts = 100.0
        scale = 2.0
        bbox_img = (0.0, 0.0, 100.0, 50.0)
        bbox_pdf = image_to_pdf_bbox(bbox_img, page_h_pts, scale)
        x1_pdf, y1_pdf, x2_pdf, y2_pdf = bbox_pdf
        assert x1_pdf == 0.0
        assert x2_pdf == 50.0
        assert y2_pdf == 100.0
        assert y1_pdf == 75.0

    def test_full_page_bbox(self):
        page_w_pts = 595.0
        page_h_pts = 842.0
        image_w = 2480
        image_h = 3508
        scale = image_w / page_w_pts
        bbox_img = (0.0, 0.0, float(image_w), float(image_h))
        bbox_pdf = image_to_pdf_bbox(bbox_img, page_h_pts, scale)
        x1, y1, x2, y2 = bbox_pdf
        assert abs(x1) < 1.0
        assert abs(y1) < 1.0
        assert abs(x2 - page_w_pts) < 1.0
        assert abs(y2 - page_h_pts) < 1.0


class TestPdfToImageBBox:
    def test_roundtrip(self):
        page_h_pts = 100.0
        scale = 2.0
        original_img = (10.0, 20.0, 50.0, 80.0)
        pdf = image_to_pdf_bbox(original_img, page_h_pts, scale)
        back = pdf_to_image_bbox(pdf, page_h_pts, scale)
        for a, b in zip(original_img, back):
            assert abs(a - b) < 1e-9

    def test_basic_conversion(self):
        page_w_pts = 595.0
        page_h_pts = 842.0
        image_w = 2480
        image_h = 3508
        scale = image_w / page_w_pts
        bbox_pdf = (0.0, 0.0, page_w_pts, page_h_pts)
        bbox_img = pdf_to_image_bbox(bbox_pdf, page_h_pts, scale)
        x1, y1, x2, y2 = bbox_img
        assert abs(x1) < 2.0
        assert abs(x2 - image_w) < 2.0
        assert abs(y1) < 2.0
        assert abs(y2 - image_h) < 2.0


# ============================================================================
# ExtractionResult
# ============================================================================

class TestExtractionResult:
    def test_default_values(self):
        result = ExtractionResult(esmiles="CCO")
        assert result.esmiles == "CCO"
        assert result.status == "pending"
        assert result.source == "image"
        assert result.composite_conf == 0.0

    def test_composite_conf_auto(self):
        result = ExtractionResult(esmiles="CCO", moldet_conf=0.9, scribe_conf=0.8)
        assert result.composite_conf == pytest.approx(0.72)

    def test_composite_conf_explicit(self):
        result = ExtractionResult(
            esmiles="CCO", moldet_conf=0.9, scribe_conf=0.8, composite_conf=0.5
        )
        assert result.composite_conf == 0.5

    def test_serialization(self):
        result = ExtractionResult(
            esmiles="c1ccccc1",
            name="benzene",
            source="image",
            moldet_conf=0.95,
            scribe_conf=0.88,
            bbox_pdf=(10.0, 20.0, 100.0, 120.0),
            page_idx=3,
            context_text="Figure 1: Benzene structure",
            mol_img_path=Path("/tmp/test.png"),
            status="pending",
        )
        d = result.to_dict()
        restored = ExtractionResult.from_dict(d)
        assert restored.esmiles == result.esmiles
        assert restored.name == result.name
        assert restored.source == result.source
        assert restored.moldet_conf == result.moldet_conf
        assert restored.scribe_conf == result.scribe_conf
        assert restored.composite_conf == pytest.approx(0.836)
        assert restored.bbox_pdf == result.bbox_pdf
        assert restored.page_idx == result.page_idx
        assert restored.context_text == result.context_text
        assert restored.mol_img_path == result.mol_img_path
        assert restored.status == result.status

    def test_serialization_no_optional(self):
        result = ExtractionResult(esmiles="O")
        d = result.to_dict()
        restored = ExtractionResult.from_dict(d)
        assert restored.bbox_pdf is None
        assert restored.mol_img_path is None
        assert restored.page_idx is None


# ============================================================================
# MolImagePipeline
# ============================================================================

class TestMolDetv2DocDetector:
    def test_unavailable_without_model(self):
        with patch(
            "mbforge.backends.moldet._has_ultralytics",
            return_value=True,
        ), patch.object(MolDetv2DocDetector, "_load_model"):
            detector = MolDetv2DocDetector.__new__(MolDetv2DocDetector)
            detector.model = None
            detector.model_path = Path("/nonexistent/model.pt")
            assert not detector.is_available()

    def test_detect_raises_when_unavailable(self):
        with patch(
            "mbforge.backends.moldet._has_ultralytics",
            return_value=True,
        ), patch.object(MolDetv2DocDetector, "_load_model"):
            detector = MolDetv2DocDetector.__new__(MolDetv2DocDetector)
            detector.model = None
            detector.model_path = Path("/nonexistent/model.pt")
            img = np.zeros((100, 100, 3), dtype=np.uint8)
            with pytest.raises(RuntimeError, match="未加载"):
                detector.detect(img)

    def test_model_path_resolution_default(self):
        with patch(
            "mbforge.backends.moldet._has_ultralytics",
            return_value=True,
        ), patch.object(MolDetv2DocDetector, "_load_model"):
            detector = MolDetv2DocDetector.__new__(MolDetv2DocDetector)
            detector.MODEL_SUBDIR = "moldetv2-doc"
            detector.DEFAULT_INPUT_SIZE = (960, 960)
            detector.device = "cpu"
            detector.conf_threshold = 0.25
            detector.iou_threshold = 0.45
            path = detector._resolve_model_path(None)
            assert "moldetv2-doc" in str(path)
            assert path.suffix in (".pt", ".onnx")


class TestMolScribeRecognizer:
    def test_unavailable_without_backend(self):
        with patch(
            "mbforge.backends.moldet._has_molscribe",
            return_value=False,
        ):
            recognizer = MolScribeRecognizer(backend="molscribe")
            assert not recognizer.is_available()

    def test_predict_raises_when_unavailable(self):
        with patch(
            "mbforge.backends.moldet._has_molscribe",
            return_value=False,
        ):
            recognizer = MolScribeRecognizer(backend="molscribe")
            img = Image.new("RGB", (100, 100))
            with pytest.raises(RuntimeError, match="不可用"):
                recognizer.predict(img)


class TestMolImagePipeline:
    def test_is_available_requires_detector(self):
        mock_det = MagicMock()
        mock_det.is_available.return_value = True
        pipeline = MolImagePipeline.__new__(MolImagePipeline)
        pipeline._gpu_disabled = False
        pipeline.doc_detector = mock_det
        pipeline.general_detector = MagicMock()
        pipeline.recognizer = MagicMock()
        assert pipeline.is_available()

    def test_is_available_false(self):
        mock_det = MagicMock()
        mock_det.is_available.return_value = False
        pipeline = MolImagePipeline.__new__(MolImagePipeline)
        pipeline._gpu_disabled = False
        pipeline.doc_detector = mock_det
        pipeline.general_detector = MagicMock()
        pipeline.recognizer = MagicMock()
        assert not pipeline.is_available()

    def test_extract_page_skips_when_unavailable(self):
        mock_det = MagicMock()
        mock_det.is_available.return_value = False
        pipeline = MolImagePipeline.__new__(MolImagePipeline)
        pipeline._gpu_disabled = False
        pipeline.doc_detector = mock_det
        pipeline.general_detector = MagicMock()
        pipeline.recognizer = MagicMock()
        pipeline.crop_cache_dir = None
        img = Image.new("RGB", (200, 200))
        results = pipeline.extract_page(
            image=img, page_idx=0, page_w_pts=100.0, page_h_pts=100.0,
            image_w=200, image_h=200,
        )
        assert results == []

    def test_extract_region_without_recognizer(self):
        pipeline = MolImagePipeline.__new__(MolImagePipeline)
        pipeline._gpu_disabled = False
        pipeline.general_detector = MagicMock()
        pipeline.general_detector.is_available.return_value = False
        pipeline.recognizer = MagicMock()
        pipeline.recognizer.is_available.return_value = False
        img = Image.new("RGB", (100, 100))
        result = pipeline.extract_region(img, page_idx=2)
        assert result.esmiles == ""
        assert result.page_idx == 2
        assert result.status == "pending"

    def test_extract_from_manual_crop(self, tmp_path):
        pipeline = MolImagePipeline.__new__(MolImagePipeline)
        pipeline._gpu_disabled = False
        pipeline.general_detector = MagicMock()
        pipeline.general_detector.is_available.return_value = False
        pipeline.recognizer = MagicMock()
        pipeline.recognizer.is_available.return_value = True
        pipeline.recognizer.predict.return_value = ("CCO", 0.9)
        page_img = Image.new("RGB", (400, 400))
        result = pipeline.extract_from_manual_crop(
            page_image=page_img,
            crop_bbox_img=(50, 50, 150, 150),
            page_idx=1,
            page_w_pts=200.0,
            page_h_pts=200.0,
            image_w=400,
            image_h=400,
        )
        assert result.esmiles == "CCO"
        assert result.scribe_conf == 0.9
        assert result.bbox_pdf is not None
        x1, y1, x2, y2 = result.bbox_pdf
        assert x1 == 25.0
        assert y1 == 125.0
        assert x2 == 75.0
        assert y2 == 175.0
