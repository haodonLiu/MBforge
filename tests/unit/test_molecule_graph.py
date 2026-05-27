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

    def test_aspirin_atom_data_fields(self):
        """Verify atom data fields (symbol, degree, charge, aromaticity) for aspirin."""
        storage = MoleculeGraphStorage()
        graph = storage.smiles_to_graph("CC(=O)Oc1ccccc1C(=O)O")

        assert graph is not None
        assert graph.atom_count == 13

        # Aspirin: CH3-CO-O-C6H4-COOH
        # Check specific atoms by index
        atoms_by_idx = {a.idx: a for a in graph.atoms}

        # Atom 0: Methyl carbon (CH3)
        assert atoms_by_idx[0].symbol == "C"
        assert atoms_by_idx[0].degree == 1
        assert atoms_by_idx[0].charge == 0
        assert atoms_by_idx[0].aromatic is False

        # Atom 1: Carbonyl carbon (C=O)
        assert atoms_by_idx[1].symbol == "C"
        assert atoms_by_idx[1].degree == 3
        assert atoms_by_idx[1].charge == 0
        assert atoms_by_idx[1].aromatic is False

        # Atom 2: Oxygen (carbonyl, degree 1)
        assert atoms_by_idx[2].symbol == "O"
        assert atoms_by_idx[2].degree == 1
        assert atoms_by_idx[2].charge == 0
        assert atoms_by_idx[2].aromatic is False

        # Atom 3: Oxygen (ester, degree 2, bridges to ring)
        assert atoms_by_idx[3].symbol == "O"
        assert atoms_by_idx[3].degree == 2
        assert atoms_by_idx[3].charge == 0
        assert atoms_by_idx[3].aromatic is False

        # Atoms 4-9: Benzene ring carbons (aromatic)
        for idx in range(4, 10):
            assert atoms_by_idx[idx].symbol == "C"
            assert atoms_by_idx[idx].aromatic is True
            assert atoms_by_idx[idx].charge == 0

        # Atom 10: Carboxyl carbon
        assert atoms_by_idx[10].symbol == "C"
        assert atoms_by_idx[10].degree == 3
        assert atoms_by_idx[10].charge == 0
        assert atoms_by_idx[10].aromatic is False

    def test_aspirin_bond_and_ring_count(self):
        """Verify bond_count and ring_count correctness for aspirin."""
        storage = MoleculeGraphStorage()
        graph = storage.smiles_to_graph("CC(=O)Oc1ccccc1C(=O)O")

        assert graph is not None
        assert graph.atom_count == 13
        # Aspirin has 13 bonds: CH3-C, C=O, C-O, O-C, 6 in ring, ring-C, C=O, C-O, O-H
        # Actually: 12 bonds in the molecule
        assert graph.bond_count == 13
        # Aspirin has 1 ring (benzene)
        assert graph.ring_count == 1
        assert len(graph.bonds) == graph.bond_count

    def test_to_dict_from_dict_roundtrip(self):
        """Test serialization round-trip preserves all data."""
        storage = MoleculeGraphStorage()
        graph = storage.smiles_to_graph("CC(=O)Oc1ccccc1C(=O)O")

        assert graph is not None

        # Convert to dict and back
        data = graph.to_dict()
        restored = GraphData.from_dict(data)

        # Verify atoms
        assert len(restored.atoms) == len(graph.atoms)
        for orig, rest in zip(graph.atoms, restored.atoms):
            assert rest.idx == orig.idx
            assert rest.symbol == orig.symbol
            assert rest.degree == orig.degree
            assert rest.charge == orig.charge
            assert rest.aromatic == orig.aromatic

        # Verify bonds
        assert len(restored.bonds) == len(graph.bonds)
        for orig, rest in zip(graph.bonds, restored.bonds):
            assert rest.begin == orig.begin
            assert rest.end == orig.end
            assert rest.bond_type == orig.bond_type
            assert rest.aromatic == orig.aromatic

        # Verify counts
        assert restored.atom_count == graph.atom_count
        assert restored.bond_count == graph.bond_count
        assert restored.ring_count == graph.ring_count

    def test_to_dict_json_serializable(self):
        """Verify to_dict output is JSON serializable."""
        storage = MoleculeGraphStorage()
        graph = storage.smiles_to_graph("CC(=O)Oc1ccccc1C(=O)O")

        assert graph is not None

        data = graph.to_dict()
        json_str = json.dumps(data)
        restored_data = json.loads(json_str)

        assert restored_data == data

    def test_from_dict_empty(self):
        """Verify from_dict handles empty/missing data gracefully."""
        graph = GraphData.from_dict({})
        assert graph.atoms == []
        assert graph.bonds == []
        assert graph.atom_count == 0
        assert graph.bond_count == 0
        assert graph.ring_count == 0
