"""Tests for MCS analyzer."""

from __future__ import annotations

import pytest
from mbforge.core.mcs_analyzer import (
    MCSAnalyzer,
    MCSResult,
)


class TestMCSAnalyzer:
    """Test MCSAnalyzer functionality."""

    def test_find_mcs_two_molecules(self):
        """Find MCS between two molecules."""
        analyzer = MCSAnalyzer()
        result = analyzer.find_mcs([
            "CC(=O)Oc1ccccc1C(=O)O",  # Aspirin
            "CC(=O)Nc1ccc(O)cc1",     # Acetaminophen
        ])

        assert result is not None
        assert result.smarts is not None
        assert result.atom_count > 0

    def test_find_mcs_single_molecule(self):
        """Single molecule should return None."""
        analyzer = MCSAnalyzer()
        result = analyzer.find_mcs(["CC(=O)Oc1ccccc1C(=O)O"])
        assert result is None

    def test_find_mcs_empty_list(self):
        """Empty list should return None."""
        analyzer = MCSAnalyzer()
        result = analyzer.find_mcs([])
        assert result is None

    def test_compute_coverage(self):
        """Should compute coverage percentages."""
        analyzer = MCSAnalyzer()
        molecules = [
            "CC(=O)Oc1ccccc1C(=O)O",
            "CC(=O)Nc1ccc(O)cc1",
        ]
        result = analyzer.find_mcs(molecules)

        assert result is not None
        assert len(result.coverage) == 2
        assert all(0 <= c <= 1 for c in result.coverage)
