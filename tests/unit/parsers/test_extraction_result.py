"""ExtractionResult 数据契约单元测试."""

from __future__ import annotations

from pathlib import Path

import pytest

from mbforge.parsers.extraction_result import ExtractionResult


class TestExtractionResult:
    """测试提取结果数据类."""

    def test_default_values(self):
        """默认状态应为 pending."""
        result = ExtractionResult(smiles="CCO")
        assert result.smiles == "CCO"
        assert result.status == "pending"
        assert result.source == "image"
        assert result.composite_conf == 0.0

    def test_composite_conf_auto(self):
        """自动计算综合置信度."""
        result = ExtractionResult(
            smiles="CCO",
            moldet_conf=0.9,
            scribe_conf=0.8,
        )
        assert result.composite_conf == pytest.approx(0.72)

    def test_composite_conf_explicit(self):
        """显式设置时不覆盖."""
        result = ExtractionResult(
            smiles="CCO",
            moldet_conf=0.9,
            scribe_conf=0.8,
            composite_conf=0.5,
        )
        assert result.composite_conf == 0.5

    def test_serialization(self):
        """序列化与反序列化."""
        result = ExtractionResult(
            smiles="c1ccccc1",
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

        assert restored.smiles == result.smiles
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
        """无可选字段的序列化."""
        result = ExtractionResult(smiles="O")
        d = result.to_dict()
        restored = ExtractionResult.from_dict(d)
        assert restored.bbox_pdf is None
        assert restored.mol_img_path is None
        assert restored.page_idx is None
