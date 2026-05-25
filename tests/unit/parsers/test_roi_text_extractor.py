"""ROITextExtractor 单元测试."""

from __future__ import annotations


from mbforge.parsers.molecule.roi_text_extractor import (
    ROITextExtractor,
    pdf_to_pdfplumber_bbox,
)


class TestPdfToPdfplumberBBox:
    """测试坐标转换."""

    def test_basic(self):
        """简单 bbox 转换."""
        bbox_pdf = (0.0, 0.0, 100.0, 100.0)
        page_h = 100.0
        pp = pdf_to_pdfplumber_bbox(bbox_pdf, page_h)
        # 左下角原点 (0,0) → 左上角原点 (0, 0)
        assert pp == (0.0, 0.0, 100.0, 100.0)

    def test_y_flip(self):
        """Y 轴翻转."""
        bbox_pdf = (10.0, 20.0, 50.0, 80.0)
        page_h = 100.0
        pp = pdf_to_pdfplumber_bbox(bbox_pdf, page_h)
        x0, top, x1, bottom = pp
        assert x0 == 10.0
        assert x1 == 50.0
        # top = 100 - 80 = 20
        assert top == 20.0
        # bottom = 100 - 20 = 80
        assert bottom == 80.0


class TestROITextExtractor:
    """测试 ROI 文本提取器（无 PDF 文件场景）."""

    def test_init(self):
        """默认参数."""
        ext = ROITextExtractor()
        assert ext.top_margin == 20.0

    def test_expand_bbox_top(self):
        """向上扩展."""
        ext = ROITextExtractor(top_margin=30.0)
        bbox = (10.0, 20.0, 50.0, 60.0)
        expanded = ext._expand_bbox(bbox, 100.0, 100.0, "top")
        # y2 增大 30，y1 不变
        assert expanded == (10.0, 20.0, 50.0, 90.0)

    def test_expand_bbox_bottom(self):
        """向下扩展."""
        ext = ROITextExtractor(bottom_margin=15.0)
        bbox = (10.0, 20.0, 50.0, 60.0)
        expanded = ext._expand_bbox(bbox, 100.0, 100.0, "bottom")
        # y1 减小 15
        assert expanded == (10.0, 5.0, 50.0, 60.0)

    def test_expand_bbox_clamping(self):
        """边界裁剪."""
        ext = ROITextExtractor(top_margin=200.0)
        bbox = (10.0, 20.0, 50.0, 60.0)
        expanded = ext._expand_bbox(bbox, 100.0, 100.0, "top")
        # y2 不能超过 page_h
        assert expanded[3] == 100.0

    def test_extract_context_no_pdfplumber(self):
        """pdfplumber 未安装时返回空字符串."""
        import mbforge.parsers.molecule.roi_text_extractor as roi_mod

        orig = roi_mod.pdfplumber
        roi_mod.pdfplumber = None
        try:
            ext = ROITextExtractor()
            result = ext.extract_context(
                __file__, 0, (0.0, 0.0, 10.0, 10.0), 100.0, 100.0
            )
            assert result == ""
        finally:
            roi_mod.pdfplumber = orig
