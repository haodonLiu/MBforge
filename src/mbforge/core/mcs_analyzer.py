"""Maximum Common Substructure analysis for OSAR design."""

from __future__ import annotations

from dataclasses import dataclass

try:
    from rdkit import Chem
    from rdkit.Chem import rdFMCS
except ImportError:
    Chem = None  # type: ignore
    rdFMCS = None  # type: ignore


@dataclass
class MCSResult:
    """MCS analysis result."""

    smarts: str
    atom_count: int
    bond_count: int
    coverage: list[float]


class MCSAnalyzer:
    """Analyze Maximum Common Substructures."""

    def find_mcs(self, molecules: list[str]) -> MCSResult | None:
        """Find MCS among a set of molecules."""
        if Chem is None or rdFMCS is None:
            return None

        if len(molecules) < 2:
            return None

        # Convert to RDKit molecules
        mols = []
        for smi in molecules:
            mol = Chem.MolFromSmiles(smi)
            if mol is not None:
                mols.append(mol)

        if len(mols) < 2:
            return None

        # Find MCS
        mcs = rdFMCS.FindMCS(
            mols,
            completeRingsOnly=True,
            matchChiralTag=True,
        )

        if mcs is None:
            return None

        # Compute coverage
        coverage = self._compute_coverage(mols, mcs.smartsString)

        return MCSResult(
            smarts=mcs.smartsString,
            atom_count=mcs.numAtoms,
            bond_count=mcs.numBonds,
            coverage=coverage,
        )

    def _compute_coverage(
        self,
        mols: list,
        smarts: str,
    ) -> list[float]:
        """Compute coverage percentage for each molecule."""
        mcs_mol = Chem.MolFromSmarts(smarts)  # type: ignore
        if mcs_mol is None:
            return [0.0] * len(mols)

        coverage = []
        for mol in mols:
            match = mol.GetSubstructMatch(mcs_mol)
            if match:
                coverage.append(len(match) / mol.GetNumAtoms())
            else:
                coverage.append(0.0)

        return coverage
