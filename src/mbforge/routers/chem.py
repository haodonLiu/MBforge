"""Chemistry operation endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

router = APIRouter()


def _validate_smiles_sync(smiles: str) -> dict:
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles(smiles)
        return {"valid": mol is not None, "smiles": smiles}
    except Exception as e:
        return {"valid": False, "error": str(e)}


@router.post("/validate-smiles")
async def validate_smiles(body: dict) -> dict:
    smiles = body.get("smiles", "")
    if not smiles:
        return {"valid": False, "error": "empty SMILES"}
    return await asyncio.to_thread(_validate_smiles_sync, smiles)


def _fingerprint_sync(smiles: str) -> dict:
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


@router.post("/fingerprint")
async def fingerprint(body: dict) -> dict:
    smiles = body.get("smiles", "")
    if not smiles:
        return {"success": False, "error": "empty SMILES"}
    return await asyncio.to_thread(_fingerprint_sync, smiles)


def _tanimoto_sync(fp_a: list, fp_b: list) -> dict:
    a = {i for i, v in enumerate(fp_a) if v}
    b = {i for i, v in enumerate(fp_b) if v}
    if not a and not b:
        return {"success": True, "similarity": 1.0}
    intersection = len(a & b)
    union = len(a | b)
    return {"success": True, "similarity": intersection / union if union else 0.0}


@router.post("/tanimoto")
async def tanimoto(body: dict) -> dict:
    fp_a = body.get("fingerprint_a", [])
    fp_b = body.get("fingerprint_b", [])
    if not fp_a or not fp_b:
        return {"success": False, "error": "two fingerprints required"}
    return await asyncio.to_thread(_tanimoto_sync, fp_a, fp_b)


def _properties_sync(smiles: str) -> dict:
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


@router.post("/properties")
async def properties(body: dict) -> dict:
    smiles = body.get("smiles", "")
    if not smiles:
        return {"success": False, "error": "empty SMILES"}
    return await asyncio.to_thread(_properties_sync, smiles)


def _canonicalize_sync(smiles: str) -> dict:
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {"success": False, "error": "invalid SMILES"}
        return {"success": True, "result": Chem.MolToSmiles(mol)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/canonicalize")
async def canonicalize(body: dict) -> dict:
    smiles = body.get("smiles", "")
    if not smiles:
        return {"success": False, "error": "empty SMILES"}
    return await asyncio.to_thread(_canonicalize_sync, smiles)


@router.post("/core-smiles")
async def core_smiles(body: dict) -> dict:
    """Extract core SMILES from E-SMILES stub."""
    return {"success": True, "result": body.get("input", "")}


@router.post("/smiles-to-molecode")
async def smiles_to_molecode(body: dict) -> dict:
    """SMILES to MoleCode stub."""
    return {"success": True, "result": ""}


@router.post("/smiles-to-esmiles")
async def smiles_to_esmiles(body: dict) -> dict:
    """SMILES to E-SMILES stub."""
    return {"success": True, "result": body.get("smiles", "")}


@router.post("/parse-esmiles-tags")
async def parse_esmiles_tags(body: dict) -> dict:
    """Parse E-SMILES tags stub."""
    return {"success": True, "smiles": body.get("input", ""), "tags": []}


@router.post("/sanitize-esmiles")
async def sanitize_esmiles(body: dict) -> dict:
    """Sanitize E-SMILES stub."""
    return {"success": True, "result": body.get("raw", "")}


@router.post("/separate-esmiles-layers")
async def separate_esmiles_layers(body: dict) -> dict:
    """Separate E-SMILES layers stub."""
    return {"success": True, "smiles": body.get("input", ""), "esmiles": None, "tags": None}


@router.post("/preprocess-smiles")
async def preprocess_smiles(body: dict) -> dict:
    """Preprocess SMILES stub."""
    return {"success": True, "result": body.get("smiles", "")}


@router.post("/preprocess-rgroup-name")
async def preprocess_rgroup_name(body: dict) -> dict:
    """Preprocess R-group name stub."""
    return {"success": True, "result": body.get("name", "")}


@router.post("/markush-parse")
async def markush_parse(body: dict) -> dict:
    """Markush parse stub."""
    return {"success": True, "core_smiles": "", "r_groups": [], "abstract_rings": [], "raw": ""}


@router.post("/markush-check")
async def markush_check(body: dict) -> dict:
    """Markush overlap check stub."""
    return {"success": True, "match_level": "NoOverlap", "core_overlap_ratio": 0.0, "matched_core_atoms": 0, "total_core_atoms": 0, "r_group_results": [], "details": []}


@router.post("/substructure-search")
async def substructure_search(body: dict) -> dict:
    """Substructure search stub."""
    return {"success": True, "results": []}


@router.post("/gesim-atom-mapping")
async def gesim_atom_mapping(body: dict) -> dict:
    """GESim atom mapping stub."""
    return {"success": True, "mapping_a": [], "mapping_b": []}
