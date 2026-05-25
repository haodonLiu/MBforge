"""AssociationEngine 单元测试."""

from __future__ import annotations

import pytest

from mbforge.parsers.association_engine import AssociationEngine
from mbforge.parsers.extraction_result import ExtractionResult


class TestAssociationEngine:
    """测试关联引擎."""

    def test_extract_compound_name(self):
        """提取化合物编号."""
        engine = AssociationEngine()
        assert engine._extract_compound_name("Compound 1") == "Compound 1"
        assert engine._extract_compound_name("Fig. 2A") == "Fig. 2A"
        assert engine._extract_compound_name("Figure 3") == "Figure 3"
        assert engine._extract_compound_name("Scheme 4") == "Scheme 4"
        assert engine._extract_compound_name("Table 5") == "Table 5"
        assert engine._extract_compound_name("no match here") is None

    def test_extract_activities_ic50(self):
        """提取 IC50 数据."""
        engine = AssociationEngine()
        acts = engine._extract_activities("IC50 = 5.2 nM")
        assert len(acts) == 1
        assert acts[0] == ("IC50", 5.2, "nM")

    def test_extract_activities_ec50(self):
        """提取 EC50 数据."""
        engine = AssociationEngine()
        acts = engine._extract_activities("EC50: 0.1 µM")
        assert len(acts) == 1
        assert acts[0][0].upper() == "EC50"
        assert acts[0][1] == 0.1

    def test_extract_activities_ki(self):
        """提取 Ki 数据."""
        engine = AssociationEngine()
        acts = engine._extract_activities("Ki of 3.4 nM")
        assert len(acts) == 1
        assert acts[0] == ("Ki", 3.4, "nM")

    def test_extract_activities_multiple(self):
        """提取多个活性数据."""
        engine = AssociationEngine()
        text = "IC50 = 5.2 nM and EC50 = 10.3 nM"
        acts = engine._extract_activities(text)
        assert len(acts) == 2
        types = {a[0].upper() for a in acts}
        assert types == {"IC50", "EC50"}

    def test_extract_activities_reverse_order(self):
        """活性类型在数值后的格式."""
        engine = AssociationEngine()
        acts = engine._extract_activities("5.2 nM (IC50)")
        assert len(acts) == 1
        assert acts[0] == ("IC50", 5.2, "nM")

    def test_associate_single(self):
        """完整关联流程."""
        engine = AssociationEngine()
        result = ExtractionResult(
            smiles="CCO",
            context_text="Compound 3 showed IC50 = 12.5 nM against A549 cells",
        )
        engine.associate_single(result)

        assert result.name == "Compound 3"
        assert result.properties["activity_type"] == "IC50"
        assert result.properties["activity_value"] == 12.5
        assert result.properties["activity_unit"] == "nM"
        assert "A549 cells" in result.properties.get("cell_lines", [])

    def test_associate_all(self):
        """批量关联."""
        engine = AssociationEngine()
        results = [
            ExtractionResult(
                smiles="CCO",
                context_text="Compound 1: IC50 = 1.0 nM",
            ),
            ExtractionResult(
                smiles="CC(=O)O",
                context_text="Compound 2: Ki = 5.0 nM",
            ),
        ]
        engine.associate_all(results)

        assert results[0].name == "Compound 1"
        assert results[0].properties["activity_type"] == "IC50"
        assert results[1].name == "Compound 2"
        assert results[1].properties["activity_type"] == "KI"

    def test_no_context(self):
        """无上下文时不报错."""
        engine = AssociationEngine()
        result = ExtractionResult(smiles="CCO", context_text="")
        engine.associate_single(result)
        assert result.name == ""
        assert result.properties == {}

    def test_unit_normalization(self):
        """单位统一."""
        engine = AssociationEngine()
        assert engine._normalize_unit("uM") == "µM"
        assert engine._normalize_unit("μm") == "µM"
        assert engine._normalize_unit("nM") == "nM"
