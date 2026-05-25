"""坐标映射模块单元测试."""

from __future__ import annotations


from mbforge.parsers.molecule.coords import (
    image_to_pdf_bbox,
    pdf_to_image_bbox,
    scale_from_page_size,
)


class TestScaleFromPageSize:
    """测试 scale 计算."""

    def test_scale_basic(self):
        """标准 A4 页面 300 DPI 渲染."""
        page_w_pts = 595.0
        page_h_pts = 842.0
        image_w = 2480  # 595 * 300 / 72 ≈ 2479
        image_h = 3508  # 842 * 300 / 72 ≈ 3508

        scale = scale_from_page_size(page_w_pts, page_h_pts, image_w, image_h)
        expected = image_w / page_w_pts
        assert abs(scale - expected) < 1e-6
        # 长宽比例一致时，两个方向的 scale 相同
        assert abs(scale - (image_h / page_h_pts)) < 0.1

    def test_scale_non_uniform(self):
        """非均匀缩放（理论上不应发生，但需容错）."""
        page_w_pts = 100.0
        page_h_pts = 100.0
        image_w = 200
        image_h = 250
        # 按宽度计算
        scale = scale_from_page_size(page_w_pts, page_h_pts, image_w, image_h)
        assert scale == 2.0


class TestImageToPdfBBox:
    """测试图像坐标 → PDF 坐标."""

    def test_basic_conversion(self):
        """简单对称情况."""
        _page_w_pts = 100.0
        page_h_pts = 100.0
        _image_w = 200
        _image_h = 200
        scale = 2.0

        # 图像左上角 (0, 0) → PDF 左下角 (0, 100)
        bbox_img = (0.0, 0.0, 100.0, 50.0)
        bbox_pdf = image_to_pdf_bbox(bbox_img, page_h_pts, scale)
        x1_pdf, y1_pdf, x2_pdf, y2_pdf = bbox_pdf

        assert x1_pdf == 0.0
        assert x2_pdf == 50.0  # 100 / 2
        # y 翻转：
        # y1_img=0 → y2_pdf = (200 - 0) / 2 = 100
        # y2_img=50 → y1_pdf = (200 - 50) / 2 = 75
        assert y2_pdf == 100.0
        assert y1_pdf == 75.0

    def test_full_page_bbox(self):
        """整页 bbox 应映射为整页 PDF rect."""
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
    """测试 PDF 坐标 → 图像坐标."""

    def test_roundtrip(self):
        """往返转换应保持一致（允许浮点误差）."""
        _page_w_pts = 100.0
        page_h_pts = 100.0
        _image_w = 200
        _image_h = 200
        scale = 2.0

        original_img = (10.0, 20.0, 50.0, 80.0)
        pdf = image_to_pdf_bbox(original_img, page_h_pts, scale)
        back = pdf_to_image_bbox(pdf, page_h_pts, scale)

        for a, b in zip(original_img, back):
            assert abs(a - b) < 1e-9

    def test_basic_conversion(self):
        """PDF rect 全页 → 图像全页."""
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
