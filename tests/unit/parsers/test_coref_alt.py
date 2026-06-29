"""coref_alt 契约测试 — bbox 必须 figure-relative 归一化 [0,1]、top-left origin。

契约来源（同时验证）：
- 前端 `projectFigureBboxToPage` (`frontend/.../CorefBboxOverlay.tsx`)：
    img y=0 在 figure 顶部 → page_y_top=figBottom
    img y=1 在 figure 底部 → page_y_top=figTop
- Rust `vlm_chem::coref_to_molecules` (line 605-622)：
    假设输入是 [0,1] 归一化 top-left
- KB `figure_labels.label_bbox` / `coref_predictions.{mol,label}_bbox`：
    前端直接当 [0,1] 归一化用

回归 bug：之前 Python 端直接存像素坐标，KB 中数值几百~几千，
前端投影时 ×fw/fh 算 page bbox，再走 pdfToCss → bbox 飞出可视区。
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PIL import Image

from mbforge.parsers.molecule.coref_alt import (
    CorefBbox,
    _contain_ratio,
    _pair_corefs,
    detect_coref_via_moldet_ocr,
)


# ============================================================================
# 端到端：detect_coref_via_moldet_ocr 输出必须在 [0, 1]
# ============================================================================


class TestBboxIsNormalized:
    """detect_coref_via_moldet_ocr 的 bbox 必须是 image-relative 归一化 [0,1]。"""

    def test_mol_bbox_normalized_to_image_size(self):
        """1600×2000 图像，像素 bbox (200, 300, 500, 600) → 归一化 (0.125, 0.15, 0.3125, 0.3)"""
        W, H = 1600, 2000
        image = Image.new("RGB", (W, H), color=0)

        doc_detector = MagicMock()
        doc_detector.detect.return_value = [
            (200, 300, 500, 600, 0.9),  # 像素坐标
        ]
        ocr_adapter = MagicMock()
        ocr_adapter.readtext.return_value = []  # 无 idt 候选

        result = detect_coref_via_moldet_ocr(image, doc_detector, ocr_adapter)

        assert len(result.bboxes) == 1
        b = result.bboxes[0]
        assert b.category_id == 1
        # 关键断言：bbox 在 [0, 1] 范围
        for v in b.bbox:
            assert 0.0 <= v <= 1.0, f"normalized value out of [0,1]: {v}"
        # 精确值
        assert b.bbox == pytest.approx(
            (200 / W, 300 / H, 500 / W, 600 / H), abs=1e-6
        )

    def test_idt_bbox_also_normalized(self):
        """RapidOCR 4 点 box → 归一化"""
        W, H = 800, 1000
        image = Image.new("RGB", (W, H), color=0)

        doc_detector = MagicMock()
        doc_detector.detect.return_value = []  # 无 mol，避免触发 contain_ratio 内部路径

        # RapidOCR 4 点输出：[(x1,y1),(x2,y2),(x3,y3),(x4,y4)]
        ocr_adapter = MagicMock()
        ocr_adapter.readtext.return_value = [
            ([[50, 50], [80, 50], [80, 70], [50, 70]], "Ia", 0.9),
        ]

        result = detect_coref_via_moldet_ocr(image, doc_detector, ocr_adapter)

        assert len(result.bboxes) == 1
        b = result.bboxes[0]
        assert b.category_id == 3
        assert b.text == "Ia"
        for v in b.bbox:
            assert 0.0 <= v <= 1.0
        # min/max 像素：(50, 50, 80, 70)
        assert b.bbox == pytest.approx(
            (50 / W, 50 / H, 80 / W, 70 / H), abs=1e-6
        )

    def test_out_of_bounds_pixels_clamped(self):
        """检测器返回超出图像边界的 bbox（如 [0, 0, 2000, 3000]）→ clamp 到 [0, 1]。

        实际场景：MolDet 在 1600×2000 图像上偶尔返回 1601 / 2001 这种舍入值。
        clamp 后保证前端投影不出 garbage。
        """
        W, H = 1600, 2000
        image = Image.new("RGB", (W, H), color=0)

        doc_detector = MagicMock()
        doc_detector.detect.return_value = [
            (-5.0, -10.0, 1700.0, 2050.0, 0.9),  # 部分超出
        ]
        ocr_adapter = MagicMock()
        ocr_adapter.readtext.return_value = []

        result = detect_coref_via_moldet_ocr(image, doc_detector, ocr_adapter)

        assert len(result.bboxes) == 1
        x1, y1, x2, y2 = result.bboxes[0].bbox
        assert x1 == 0.0
        assert y1 == 0.0
        assert x2 == 1.0
        assert y2 == 1.0

    def test_empty_inputs_return_empty_result(self):
        """无 mol / 无 idt → 空结果，corefs = []。"""
        image = Image.new("RGB", (800, 1000), color=0)
        doc_detector = MagicMock()
        doc_detector.detect.return_value = []
        ocr_adapter = MagicMock()
        ocr_adapter.readtext.return_value = []

        result = detect_coref_via_moldet_ocr(image, doc_detector, ocr_adapter)

        assert result.bboxes == []
        assert result.corefs == []

    def test_distant_idt_excluded(self):
        """idt 中心离 mol > 30% 页面 → 排除。"""
        bboxes = [
            CorefBbox(category_id=1, bbox=(0.10, 0.10, 0.20, 0.20), score=0.9),
            CorefBbox(category_id=3, bbox=(0.85, 0.10, 0.90, 0.15), text="99", score=0.8),
        ]
        pairs = _pair_corefs(bboxes, [0], [1], 1000, 1000, 612.0, 792.0)
        assert pairs == []

    def test_idt_inside_mol_excluded_by_iou(self):
        """idt bbox 与 mol bbox 重叠（IoU > 0）→ 排除（视为分子内部元素）。"""
        bboxes = [
            CorefBbox(category_id=1, bbox=(0.10, 0.10, 0.30, 0.30), score=0.9),
            # idt 完全在 mol 内部
            CorefBbox(category_id=3, bbox=(0.15, 0.15, 0.20, 0.20), text="C", score=0.7),
        ]
        pairs = _pair_corefs(bboxes, [0], [1], 1000, 1000, 612.0, 792.0)
        assert pairs == []

    def test_each_mol_used_at_most_once(self):
        """贪心配对：一个 mol 只能配一个 idt（按 idt 置信度优先）。"""
        bboxes = [
            CorefBbox(category_id=1, bbox=(0.10, 0.10, 0.20, 0.20), score=0.9),  # mol
            CorefBbox(category_id=3, bbox=(0.25, 0.12, 0.30, 0.16), text="1", score=0.9),  # 高分
            CorefBbox(category_id=3, bbox=(0.05, 0.12, 0.08, 0.16), text="2", score=0.7),  # 低分
        ]
        pairs = _pair_corefs(bboxes, [0], [1, 2], 1000, 1000, 612.0, 792.0)
        # 只有一个 mol，所以最多一个 pair
        assert len(pairs) == 1
        # 高分 idt 优先
        assert pairs[0][1] == 1


# ============================================================================
# _contain_ratio: 必须同坐标系（修复前的回归点）
# ============================================================================


class TestContainRatioSameCoords:
    """_contain_ratio 假设 inner/outer 同坐标系。"""

    def test_fully_inside_returns_one(self):
        inner = (0.1, 0.1, 0.2, 0.2)
        outer = (0.0, 0.0, 1.0, 1.0)
        assert _contain_ratio(inner, outer) == pytest.approx(1.0, abs=1e-6)

    def test_partial_overlap(self):
        inner = (0.1, 0.1, 0.3, 0.3)  # 面积 0.04
        outer = (0.2, 0.2, 0.4, 0.4)  # 交集 (0.2,0.2,0.3,0.3) 面积 0.01
        assert _contain_ratio(inner, outer) == pytest.approx(0.25, abs=1e-6)

    def test_no_overlap_returns_zero(self):
        assert _contain_ratio((0.0, 0.0, 0.1, 0.1), (0.5, 0.5, 0.6, 0.6)) == 0.0

