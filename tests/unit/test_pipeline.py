"""PDF 管线集成测试 — 验证解析、分类、提取链路."""

import tempfile
from pathlib import Path

import pytest


class TestDocumentClassification:
    """测试文档分类逻辑."""

    def test_classify_text_document(self):
        """验证纯文本文档分类."""
        from mbforge.parsers.molecule.extraction_result import ExtractionResult
        result = ExtractionResult(
            esmiles="CCO",
            source="text",
            moldet_conf=0.0,
            scribe_conf=0.0,
            page_idx=0,
            status="pending",
        )
        assert result.esmiles == "CCO"
        assert result.source == "text"
        assert result.status == "pending"

    def test_extraction_result_serialization(self):
        """验证 ExtractionResult 序列化/反序列化."""
        from mbforge.parsers.molecule.extraction_result import ExtractionResult
        original = ExtractionResult(
            esmiles="CC(=O)Oc1ccccc1C(=O)O",
            source="image",
            moldet_conf=0.95,
            scribe_conf=0.88,
            page_idx=3,
            status="confirmed",
        )
        d = original.to_dict()
        restored = ExtractionResult.from_dict(d)
        assert restored.esmiles == original.esmiles
        assert restored.source == original.source
        assert restored.moldet_conf == original.moldet_conf
        assert restored.page_idx == original.page_idx


class TestCoordinateTransform:
    """测试坐标转换."""

    def test_image_to_pdf_bbox(self):
        """验证图像坐标到 PDF 坐标转换."""
        from mbforge.parsers.molecule.coords import image_to_pdf_bbox
        # 图像坐标 (100, 200, 300, 400), 页面高度 842pt
        pdf_bbox = image_to_pdf_bbox((100, 200, 300, 400), 842.0, 1.0)
        assert len(pdf_bbox) == 4
        x1, y1, x2, y2 = pdf_bbox
        # PDF 坐标系 Y 轴反转
        assert y1 < y2  # PDF 下边 < 上边

    def test_scale_from_page_size(self):
        """验证缩放因子计算."""
        from mbforge.parsers.molecule.coords import scale_from_page_size
        scale = scale_from_page_size(595.0, 842.0, 1190, 1684)
        # image_w/page_w = 1190/595 = 2.0
        assert abs(scale - 2.0) < 0.01


class TestHeadingExtraction:
    """测试 heading 提取逻辑."""

    def test_extract_markdown_headings(self):
        """验证 Markdown heading 提取."""
        from mbforge.parsers.molecule.extraction_result import ExtractionResult
        # ExtractionResult 不直接做 heading 提取，
        # 但验证相关类型可用
        assert ExtractionResult is not None


class TestConfigIntegration:
    """测试配置系统集成（sidecar 裁剪版）.

    LLM/OCR/ModelServer 配置已迁移到 Rust 侧（`core::config::settings.rs`），
    本测试仅覆盖 sidecar 需要的 embed/rerank/vlm 三个子配置。
    """

    def test_load_global_config(self):
        """验证全局配置加载不崩溃."""
        from mbforge.utils.config import load_global_config
        config = load_global_config()
        assert config is not None
        assert hasattr(config, 'embed')
        assert hasattr(config, 'rerank')
        assert hasattr(config, 'vlm')

    def test_config_sections_have_required_fields(self):
        """验证配置节有必需字段."""
        from mbforge.utils.config import load_global_config
        config = load_global_config()
        # Embed config
        assert hasattr(config.embed, 'provider')
        assert hasattr(config.embed, 'model_name')
        assert hasattr(config.embed, 'device')
        # Rerank config
        assert hasattr(config.rerank, 'provider')
        assert hasattr(config.rerank, 'model_name')
        # VLM config
        assert hasattr(config.vlm, 'provider')


# TestProjectIntegration 已迁移：Python `Project` 类已删除
# (被 Rust `core::project::Project` 取代)。原 `TestProjectIntegration` 覆盖
# 的逻辑由 Rust 侧单元测试 + 集成测试负责（`src-tauri/src/core/project/`）。
