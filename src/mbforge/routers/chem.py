"""Chemistry operation endpoints."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.post("/validate-smiles")
async def validate_smiles(body: dict) -> dict:
    smiles = body.get("smiles", "")
    if not smiles:
        return {"valid": False, "error": "empty SMILES"}
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles(smiles)
        return {"valid": mol is not None, "smiles": smiles}
    except Exception as e:
        return {"valid": False, "error": str(e)}


@router.post("/fingerprint")
async def fingerprint(body: dict) -> dict:
    smiles = body.get("smiles", "")
    if not smiles:
        return {"success": False, "error": "empty SMILES"}
    try:
        import numpy as np
        from rdkit import Chem
        from rdkit.Chem import AllChem

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"success": False, "error": "invalid SMILES"}
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
        arr = np.array(fp, dtype=np.uint8)
        return {"success": True, "fingerprint": arr.tolist(), "bits": int(arr.sum())}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/tanimoto")
async def tanimoto(body: dict) -> dict:
    fp_a = body.get("fingerprint_a", [])
    fp_b = body.get("fingerprint_b", [])
    if not fp_a or not fp_b:
        return {"success": False, "error": "two fingerprints required"}
    a = set(i for i, v in enumerate(fp_a) if v)
    b = set(i for i, v in enumerate(fp_b) if v)
    if not a and not b:
        return {"success": True, "similarity": 1.0}
    intersection = len(a & b)
    union = len(a | b)
    return {"success": True, "similarity": intersection / union if union else 0.0}


@router.post("/properties")
async def properties(body: dict) -> dict:
    smiles = body.get("smiles", "")
    if not smiles:
        return {"success": False, "error": "empty SMILES"}
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"success": False, "error": "invalid SMILES"}
        return {
            "success": True,
            "properties": {
                "molecular_weight": round(Descriptors.MolWt(mol), 2),
                "logp": round(Descriptors.MolLogP(mol), 2),
                "hbd": rdMolDescriptors.CalcNumHBD(mol),
                "hba": rdMolDescriptors.CalcNumHBA(mol),
                "tpsa": round(Descriptors.TPSA(mol), 2),
                "rotatable_bonds": rdMolDescriptors.CalcNumRotatableBonds(mol),
                "aromatic_rings": rdMolDescriptors.CalcNumAromaticRings(mol),
                "formula": rdMolDescriptors.CalcMolFormula(mol),
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
