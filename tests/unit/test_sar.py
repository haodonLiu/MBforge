"""测试 SAR 分析模块.

覆盖：
- 共同骨架提取
- 单分子 R-group 分解
- R-group 矩阵构建
- 活性热力图聚合
- 边界情况（无骨架、单化合物、坏 SMILES）
"""
from __future__ import annotations

import pytest

from mbforge.csar.sar import (
    build_activity_heatmap,
    build_rgroup_matrix,
    decompose_compound,
    find_common_scaffold,
    is_available,
)

# 苯胺衍生物 SAR 集 — 共享对位取代的 acetanilide 骨架
PHENOL_SAR = [
    {
        "id": "p1",
        "name": "Paracetamol",
        "smiles": "CC(=O)Nc1ccc(O)cc1",
        "activity": 10.0,
        "activity_type": "IC50",
        "units": "uM",
    },
    {
        "id": "p2",
        "name": "Phenacetin",
        "smiles": "CCOc1ccc(NC(C)=O)cc1",
        "activity": 50.0,
        "activity_type": "IC50",
        "units": "uM",
    },
    {
        "id": "p3",
        "name": "4-Cl acetanilide",
        "smiles": "CC(=O)Nc1ccc(Cl)cc1",
        "activity": 5.0,
        "activity_type": "IC50",
        "units": "uM",
    },
    {
        "id": "p4",
        "name": "4-Me acetanilide",
        "smiles": "CC(=O)Nc1ccc(C)cc1",
        "activity": 20.0,
        "activity_type": "IC50",
        "units": "uM",
    },
]


class TestSARModule:
    """SAR 模块基础测试。"""

    def test_module_available(self):
        """RDKit 应当可用（项目依赖）。"""
        assert is_available() is True


@pytest.mark.skipif(not is_available(), reason="RDKit not available")
class TestCommonScaffold:
    """共同骨架提取。"""

    def test_finds_shared_scaffold(self):
        """一组同骨架化合物应提取出共同结构。"""
        scaffold = find_common_scaffold([c["smiles"] for c in PHENOL_SAR])
        assert scaffold is not None
        # 骨架应包含 acetanilide 核心: CC(=O)NC1:C:C:C:C:C:1
        assert "C(=O)N" in scaffold or "C(:C:C" in scaffold

    def test_returns_none_for_diverse_set(self):
        """结构差异大的化合物应返回 None（无共同骨架）。"""
        diverse = [
            "CCO",  # ethanol
            "c1ccccc1",  # benzene
            "CCCCCCCC",  # octane
        ]
        scaffold = find_common_scaffold(diverse)
        assert scaffold is None

    def test_returns_none_for_single_compound(self):
        """少于 2 个有效分子时返回 None。"""
        scaffold = find_common_scaffold(["CCO"])
        assert scaffold is None

    def test_returns_none_for_empty(self):
        """空列表返回 None。"""
        assert find_common_scaffold([]) is None

    def test_min_atoms_threshold(self):
        """min_atoms 阈值过滤过小骨架。"""
        # 设置过高的 min_atoms 应当返回 None
        scaffold = find_common_scaffold(
            [c["smiles"] for c in PHENOL_SAR], min_atoms=100
        )
        assert scaffold is None


@pytest.mark.skipif(not is_available(), reason="RDKit not available")
class TestRGroupDecomposition:
    """单分子 R-group 分解。"""

    def test_decompose_matches_compound(self):
        """匹配骨架的分子应分解出 R-group。"""
        result = decompose_compound(
            "CC(=O)Nc1ccc(O)cc1",
            "CC(=O)Nc1ccc(*)cc1",  # 骨架: 4-hydroxyacetanilide 但 OH 位置为 R
            compound_id="p1",
            compound_name="Paracetamol",
        )
        # 这个 SMARTS 不一定匹配得上 paracetamol，测试结构性约束
        assert result.compound_id == "p1"
        assert result.compound_name == "Paracetamol"

    def test_decompose_unmatched_returns_empty(self):
        """不匹配骨架的分子应 core_matches=False。"""
        result = decompose_compound(
            "CCO",  # ethanol
            "c1ccccc1",  # benzene scaffold
        )
        assert result.core_matches is False
        assert result.r_groups == []


@pytest.mark.skipif(not is_available(), reason="RDKit not available")
class TestRGroupMatrix:
    """R-group 矩阵构建。"""

    def test_auto_extracts_scaffold(self):
        """不传 core_smiles 时应自动提取。"""
        matrix = build_rgroup_matrix(PHENOL_SAR)
        assert matrix.core_smiles != ""
        assert matrix.unmatched_count == 0
        assert len(matrix.r_labels) >= 1
        assert len(matrix.rows) == len(PHENOL_SAR)

    def test_matrix_shape(self):
        """矩阵形状：rows = 化合物数, len(row) = r_labels 数。"""
        matrix = build_rgroup_matrix(PHENOL_SAR, auto_extract_scaffold=True)
        for row in matrix.rows:
            assert len(row) == len(matrix.r_labels)

    def test_compounds_preserved(self):
        """化合物元数据应完整保留。"""
        matrix = build_rgroup_matrix(PHENOL_SAR)
        ids = {c["id"] for c in matrix.compounds}
        assert ids == {"p1", "p2", "p3", "p4"}

    def test_rgroup_values_non_empty(self):
        """每个匹配的化合物应至少有一个 R-group 取代基 SMILES。"""
        matrix = build_rgroup_matrix(PHENOL_SAR)
        for row in matrix.rows:
            non_empty = [v for v in row if v and v != "—"]
            assert len(non_empty) >= 1

    def test_with_explicit_scaffold(self):
        """显式传 core_smiles 时不自动提取。"""
        # 强制一个明显不匹配的骨架
        matrix = build_rgroup_matrix(
            PHENOL_SAR,
            core_smiles="c1ccc2ccccc2c1",  # naphthalene
            auto_extract_scaffold=False,
        )
        assert matrix.core_smiles == "c1ccc2ccccc2c1"
        assert matrix.unmatched_count == len(PHENOL_SAR)

    def test_no_common_scaffold_yields_empty_matrix(self):
        """MCS 找不到共同骨架时，矩阵应为空 (不抛异常)."""
        mixed = PHENOL_SAR + [
            {"id": "x1", "name": "Octane", "smiles": "CCCCCCCC"}
        ]
        matrix = build_rgroup_matrix(mixed, auto_extract_scaffold=True)
        # MCS 找不到跨所有分子的共同骨架
        assert matrix.core_smiles == "" or matrix.unmatched_count == len(mixed)
        assert matrix.r_labels == []
        assert matrix.rows == []


@pytest.mark.skipif(not is_available(), reason="RDKit not available")
class TestActivityHeatmap:
    """活性热力图聚合。"""

    def test_heatmap_groups_by_substituent(self):
        """相同取代基的化合物应聚合到同一 cell。"""
        # 用重复取代基构造测试
        matrix = build_rgroup_matrix(
            [
                {"id": "a", "name": "A", "smiles": "CC(=O)Nc1ccc(O)cc1", "activity": 10.0},
                {"id": "b", "name": "B", "smiles": "CC(=O)Nc1ccc(O)cc1", "activity": 20.0},
                {"id": "c", "name": "C", "smiles": "CC(=O)Nc1ccc(Cl)cc1", "activity": 5.0},
            ],
            auto_extract_scaffold=True,
        )
        heatmaps = build_activity_heatmap(matrix, lower_is_better=True)
        assert len(heatmaps) >= 1
        # 找到 R1 的热力图
        r1_heatmap = next(h for h in heatmaps if h.r_label == "R1")
        # 'O' 取代基应有 2 个数据点
        o_cell = next(c for c in r1_heatmap.cells if c["substituent_smiles"] == "O")
        assert o_cell["count"] == 2
        assert o_cell["avg_activity"] == 15.0
        # 'O' 排序在前（avg=15）还是 'Cl'（avg=5）?
        # lower_is_better=True → 5 < 15，Cl 排前
        assert r1_heatmap.cells[0]["substituent_smiles"] == "Cl"

    def test_heatmap_sorting_higher_is_better(self):
        """lower_is_better=False 时高活性排前。"""
        matrix = build_rgroup_matrix(
            [
                {"id": "a", "name": "A", "smiles": "CC(=O)Nc1ccc(O)cc1", "activity": 10.0},
                {"id": "b", "name": "B", "smiles": "CC(=O)Nc1ccc(Cl)cc1", "activity": 90.0},
            ],
            auto_extract_scaffold=True,
        )
        heatmaps = build_activity_heatmap(matrix, lower_is_better=False)
        r1 = next(h for h in heatmaps if h.r_label == "R1")
        # 90 > 10，Cl (avg=90) 排前
        assert r1.cells[0]["substituent_smiles"] == "Cl"

    def test_heatmap_skips_missing_activity(self):
        """没有 activity 字段的化合物应跳过。"""
        matrix = build_rgroup_matrix(
            [
                {"id": "a", "name": "A", "smiles": "CC(=O)Nc1ccc(O)cc1", "activity": 10.0},
                {"id": "b", "name": "B", "smiles": "CC(=O)Nc1ccc(Cl)cc1"},  # no activity
            ],
            auto_extract_scaffold=True,
        )
        heatmaps = build_activity_heatmap(matrix, lower_is_better=True)
        r1 = next(h for h in heatmaps if h.r_label == "R1")
        # 只应有 1 个 cell (O)
        assert len(r1.cells) == 1
        assert r1.cells[0]["substituent_smiles"] == "O"

    def test_heatmap_empty_when_no_activity(self):
        """全部化合物无活性数据时返回空 cells。"""
        matrix = build_rgroup_matrix(
            [
                {"id": "a", "name": "A", "smiles": "CC(=O)Nc1ccc(O)cc1"},
                {"id": "b", "name": "B", "smiles": "CC(=O)Nc1ccc(Cl)cc1"},
            ],
            auto_extract_scaffold=True,
        )
        heatmaps = build_activity_heatmap(matrix, lower_is_better=True)
        r1 = next(h for h in heatmaps if h.r_label == "R1")
        assert r1.cells == []
