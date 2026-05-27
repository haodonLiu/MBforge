"""Tests for molecule graph storage."""

from __future__ import annotations

import json
import pytest
from mbforge.core.molecule_graph import (
    MoleculeGraphStorage,
    GraphData,
)


class TestMoleculeGraphStorage:
    """Test MoleculeGraphStorage functionality."""

    def test_mol_to_graph_aspirin(self):
        """Convert aspirin SMILES to graph."""
        storage = MoleculeGraphStorage()
        graph = storage.smiles_to_graph("CC(=O)Oc1ccccc1C(=O)O")

        assert graph is not None
        assert len(graph.atoms) > 0
        assert len(graph.bonds) > 0
        assert graph.atom_count == 13  # Aspirin has 13 atoms

    def test_mol_to_graph_invalid_smiles(self):
        """Invalid SMILES should return None."""
        storage = MoleculeGraphStorage()
        graph = storage.smiles_to_graph("INVALID_SMILES")
        assert graph is None

    def test_compute_mcs_fingerprint(self):
        """Should compute MCS fingerprint."""
        storage = MoleculeGraphStorage()
        fp = storage.compute_mcs_fingerprint("CC(=O)Oc1ccccc1C(=O)O")
        assert fp is not None
        assert len(fp) > 0
