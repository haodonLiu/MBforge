"""MolImagePipeline 单元测试（无模型场景）."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from mbforge.parsers.molecule.mol_image_pipeline import (
    MolDetv2DocDetector,
    MolImagePipeline,
    MolScribeRecognizer,
)


class TestMolDetv2DocDetector:
    """测试 Doc 版检测器（无模型）."""

    def test_unavailable_without_model(self):
        """模型不存在时 is_available 为 False."""
        with patch(
            "mbforge.parsers.molecule.mol_image_pipeline._HAS_ULTRALYTICS", True
        ), patch.object(MolDetv2DocDetector, "_load_model"):
            detector = MolDetv2DocDetector.__new__(MolDetv2DocDetector)
            detector.model = None
            detector.model_path = Path("/nonexistent/model.pt")
            assert not detector.is_available()

    def test_detect_raises_when_unavailable(self):
        """不可用时调用 detect 应抛异常."""
        with patch(
            "mbforge.parsers.molecule.mol_image_pipeline._HAS_ULTRALYTICS", True
        ), patch.object(MolDetv2DocDetector, "_load_model"):
            detector = MolDetv2DocDetector.__new__(MolDetv2DocDetector)
            detector.model = None
            detector.model_path = Path("/nonexistent/model.pt")
            img = np.zeros((100, 100, 3), dtype=np.uint8)
            with pytest.raises(RuntimeError, match="未加载"):
                detector.detect(img)

    def test_model_path_resolution_default(self):
        """默认模型路径解析."""
        with patch(
            "mbforge.parsers.molecule.mol_image_pipeline._HAS_ULTRALYTICS", True
        ), patch.object(MolDetv2DocDetector, "_load_model"):
            detector = MolDetv2DocDetector.__new__(MolDetv2DocDetector)
            detector.MODEL_SUBDIR = "moldetv2-doc"
            detector.DEFAULT_INPUT_SIZE = (960, 960)
            detector.device = "cpu"
            detector.conf_threshold = 0.25
            detector.iou_threshold = 0.45
            path = detector._resolve_model_path(None)
            assert "moldetv2-doc" in str(path)
            # 现在能匹配到实际下载的文件名
            assert path.suffix in (".pt", ".onnx")


class TestMolScribeRecognizer:
    """测试 MolScribe 识别器（无模型）."""

    def test_unavailable_without_backend(self):
        """无后端时 is_available 为 False."""
        with patch(
            "mbforge.parsers.molecule.mol_image_pipeline._HAS_MOLSCRIBE", False
        ):
            recognizer = MolScribeRecognizer(backend="molscribe")
            assert not recognizer.is_available()

    def test_predict_raises_when_unavailable(self):
        """不可用时调用 predict 应抛异常."""
        with patch(
            "mbforge.parsers.molecule.mol_image_pipeline._HAS_MOLSCRIBE", False
        ):
            recognizer = MolScribeRecognizer(backend="molscribe")
            img = Image.new("RGB", (100, 100))
            with pytest.raises(RuntimeError, match="不可用"):
                recognizer.predict(img)


class TestMolImagePipeline:
    """测试主管线接口."""

    def test_is_available_requires_detector(self):
        """管线可用性取决于检测器."""
        mock_det = MagicMock()
        mock_det.is_available.return_value = True
        pipeline = MolImagePipeline.__new__(MolImagePipeline)
        pipeline.mol_image_pipeline = None
        pipeline.doc_detector = mock_det
        pipeline.general_detector = MagicMock()
        pipeline.recognizer = MagicMock()
        assert pipeline.is_available()

    def test_is_available_false(self):
        """检测器不可用时管线不可用."""
        mock_det = MagicMock()
        mock_det.is_available.return_value = False
        pipeline = MolImagePipeline.__new__(MolImagePipeline)
        pipeline.doc_detector = mock_det
        pipeline.general_detector = MagicMock()
        pipeline.recognizer = MagicMock()
        assert not pipeline.is_available()

    def test_extract_page_skips_when_unavailable(self):
        """管线不可用时 extract_page 返回空列表."""
        mock_det = MagicMock()
        mock_det.is_available.return_value = False
        pipeline = MolImagePipeline.__new__(MolImagePipeline)
        pipeline.doc_detector = mock_det
        pipeline.general_detector = MagicMock()
        pipeline.recognizer = MagicMock()
        pipeline.crop_cache_dir = None

        img = Image.new("RGB", (200, 200))
        results = pipeline.extract_page(
            image=img,
            page_idx=0,
            page_w_pts=100.0,
            page_h_pts=100.0,
            image_w=200,
            image_h=200,
        )
        assert results == []

    def test_extract_region_without_recognizer(self):
        """无识别器时 extract_region 返回空 SMILES."""
        pipeline = MolImagePipeline.__new__(MolImagePipeline)
        pipeline.general_detector = MagicMock()
        pipeline.general_detector.is_available.return_value = False
        pipeline.recognizer = MagicMock()
        pipeline.recognizer.is_available.return_value = False

        img = Image.new("RGB", (100, 100))
        result = pipeline.extract_region(img, page_idx=2)
        assert result.smiles == ""
        assert result.page_idx == 2
        assert result.status == "pending"

    def test_extract_from_manual_crop(self, tmp_path):
        """手动框选区域提取."""
        pipeline = MolImagePipeline.__new__(MolImagePipeline)
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
        assert result.smiles == "CCO"
        assert result.scribe_conf == 0.9
        assert result.bbox_pdf is not None
        # 验证坐标映射：
        # scale = 400 / 200 = 2
        # x1_pdf = 50 / 2 = 25
        # y1_pdf = (400 - 150) / 2 = 125
        # x2_pdf = 150 / 2 = 75
        # y2_pdf = (400 - 50) / 2 = 175
        x1, y1, x2, y2 = result.bbox_pdf
        assert x1 == 25.0
        assert y1 == 125.0
        assert x2 == 75.0
        assert y2 == 175.0
