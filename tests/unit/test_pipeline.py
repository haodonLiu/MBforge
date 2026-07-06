"""PDF 管线集成测试 — 验证解析、分类、提取链路."""



from mbforge.utils.logger import get_logger

logger = get_logger(__name__)


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


# TestConfigIntegration 已删除：Qwen-era embed/rerank/EmbedConfig/RerankConfig
# 在 KB 迁移到 OpenKB + PageIndex 后全部移除,配置 schema 不再有这些字段。
# 新的统一 schema 由 tests/unit/test_config.py 覆盖。
# TestProjectIntegration 已迁移：Python `Project` 类已删除
# (被 Rust `core::project::Project` 取代)。原 `TestProjectIntegration` 覆盖
# 的逻辑由 Rust 侧单元测试 + 集成测试负责（`src-tauri/src/core/project/`）。
