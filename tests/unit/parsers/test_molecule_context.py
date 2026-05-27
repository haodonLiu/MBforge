"""Tests for molecule context extraction."""

from __future__ import annotations

import pytest
from mbforge.parsers.molecule_context import (
    MoleculeContextExtractor,
    MoleculeContext,
)


class TestMoleculeContextExtractor:
    """Test MoleculeContextExtractor functionality."""

    def test_extract_context_smiles_mention(self):
        """Extract context around SMILES mention."""
        extractor = MoleculeContextExtractor()
        text = "The compound CC(=O)Oc1ccccc1C(=O)O showed activity."
        contexts = extractor.extract_contexts(
            text,
            smiles="CC(=O)Oc1ccccc1C(=O)O",
        )

        assert len(contexts) > 0
        assert contexts[0].context_type == "smiles_mention"

    def test_extract_context_name_mention(self):
        """Extract context around chemical name mention."""
        extractor = MoleculeContextExtractor()
        text = "Aspirin is a common pain reliever."
        contexts = extractor.extract_contexts(
            text,
            smiles="CC(=O)Oc1ccccc1C(=O)O",
            name="Aspirin",
        )

        assert len(contexts) > 0
        assert contexts[0].context_type == "name_mention"

    def test_extract_context_activity_data(self):
        """Extract context around activity data."""
        extractor = MoleculeContextExtractor()
        text = "IC50 = 5.2 nM for this compound."
        contexts = extractor.extract_contexts(
            text,
            smiles="CC(=O)Oc1ccccc1C(=O)O",
            activities=[{"type": "IC50", "value": 5.2, "units": "nM"}],
        )

        assert len(contexts) > 0

    def test_deduplicate_contexts(self):
        """Should deduplicate overlapping contexts."""
        extractor = MoleculeContextExtractor()
        text = "Aspirin (CC(=O)Oc1ccccc1C(=O)O) is effective."
        contexts = extractor.extract_contexts(
            text,
            smiles="CC(=O)Oc1ccccc1C(=O)O",
            name="Aspirin",
        )

        # Should not have duplicate contexts for overlapping mentions
        assert len(contexts) <= 2
