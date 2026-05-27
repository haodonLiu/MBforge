"""Molecule graph storage for substructure matching."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdFMCS
except ImportError:
    Chem = None  # type: ignore
    AllChem = None  # type: ignore
    rdFMCS = None  # type: ignore


@dataclass
class AtomData:
    """Atom data in graph."""

    idx: int
    symbol: str
    degree: int
    charge: int
    aromatic: bool


@dataclass
class BondData:
    """Bond data in graph."""

    begin: int
    end: int
    bond_type: int
    aromatic: bool


@dataclass
class GraphData:
    """Molecular graph representation."""

    atoms: list[AtomData] = field(default_factory=list)
    bonds: list[BondData] = field(default_factory=list)
    atom_count: int = 0
    bond_count: int = 0
    ring_count: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "atoms": [
                {
                    "idx": a.idx,
                    "symbol": a.symbol,
                    "degree": a.degree,
                    "charge": a.charge,
                    "aromatic": a.aromatic,
                }
                for a in self.atoms
            ],
            "bonds": [
                {
                    "begin": b.begin,
                    "end": b.end,
                    "bond_type": b.bond_type,
                    "aromatic": b.aromatic,
                }
                for b in self.bonds
            ],
            "atom_count": self.atom_count,
            "bond_count": self.bond_count,
            "ring_count": self.ring_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> GraphData:
        """Create from dictionary."""
        return cls(
            atoms=[AtomData(**a) for a in data.get("atoms", [])],
            bonds=[BondData(**b) for b in data.get("bonds", [])],
            atom_count=data.get("atom_count", 0),
            bond_count=data.get("bond_count", 0),
            ring_count=data.get("ring_count", 0),
        )


class MoleculeGraphStorage:
    """Store molecules with graph structures."""

    def smiles_to_graph(self, smiles: str) -> GraphData | None:
        """Convert SMILES to graph representation."""
        if Chem is None:
            return None

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None

        return self._mol_to_graph(mol)

    def _mol_to_graph(self, mol) -> GraphData:
        """Convert RDKit molecule to graph."""
        graph = GraphData()

        for atom in mol.GetAtoms():
            graph.atoms.append(
                AtomData(
                    idx=atom.GetIdx(),
                    symbol=atom.GetSymbol(),
                    degree=atom.GetDegree(),
                    charge=atom.GetFormalCharge(),
                    aromatic=atom.GetIsAromatic(),
                )
            )

        for bond in mol.GetBonds():
            graph.bonds.append(
                BondData(
                    begin=bond.GetBeginAtomIdx(),
                    end=bond.GetEndAtomIdx(),
                    bond_type=int(bond.GetBondType()),
                    aromatic=bond.GetIsAromatic(),
                )
            )

        graph.atom_count = mol.GetNumAtoms()
        graph.bond_count = mol.GetNumBonds()
        graph.ring_count = len(mol.GetRingInfo().AtomRings())

        return graph

    def compute_mcs_fingerprint(self, smiles: str) -> str | None:
        """Compute fingerprint using Morgan radius 2.

        Note: rdFMCS.FindMCS requires at least 2 molecules to compute a true
        maximum common substructure. Since this method operates on a single
        molecule, it generates a Morgan fingerprint (radius 2, 1024 bits) as
        a structural descriptor. For true MCS-based fingerprinting between
        molecule pairs, use compute_mcs_fingerprint_pair() instead.
        """
        if Chem is None or AllChem is None:
            return None

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None

        fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=1024)
        return fp.ToBitString()

    def compute_mcs_fingerprint_pair(
        self, smiles1: str, smiles2: str
    ) -> str | None:
        """Compute MCS-based fingerprint between two molecules.

        Uses rdFMCS.FindMCS to identify the maximum common substructure
        between two molecules, then generates a Morgan fingerprint from
        that shared substructure pattern.
        """
        if Chem is None or rdFMCS is None or AllChem is None:
            return None

        mol1 = Chem.MolFromSmiles(smiles1)
        mol2 = Chem.MolFromSmiles(smiles2)
        if mol1 is None or mol2 is None:
            return None

        mcs_result = rdFMCS.FindMCS([mol1, mol2])
        if mcs_result.numAtoms == 0:
            return None

        mcs_mol = Chem.MolFromSmarts(mcs_result.smartsString)
        if mcs_mol is None:
            return None

        fp = AllChem.GetMorganFingerprintAsBitVect(mcs_mol, 2, nBits=1024)
        return fp.ToBitString()
