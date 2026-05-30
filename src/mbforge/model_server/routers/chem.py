"""Chemistry路由."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ...utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem

    _RDKI_AVAILABLE = True
except ImportError:
    _RDKI_AVAILABLE = False


class TanimotoRequest(BaseModel):
    smiles1: str
    smiles2: str


class TanimotoResponse(BaseModel):
    success: bool
    smiles1: str
    smiles2: str
    tanimoto: float | None
    error: str | None = None


def _compute_tanimoto(s1: str, s2: str) -> float | None:
    if not _RDKI_AVAILABLE:
        return None
    try:
        mol1 = Chem.MolFromSmiles(s1)
        mol2 = Chem.MolFromSmiles(s2)
        if mol1 is None or mol2 is None:
            return None
        fp1 = AllChem.GetMorganFingerprintAsBitVect(mol1, 2, nBits=2048)
        fp2 = AllChem.GetMorganFingerprintAsBitVect(mol2, 2, nBits=2048)
        return float(fp1.TanimotoSimilarity(fp2))
    except Exception:
        return None


@router.post("/tanimoto", response_model=TanimotoResponse)
async def tanimoto_similarity(request: TanimotoRequest) -> TanimotoResponse:
    if not _RDKI_AVAILABLE:
        return TanimotoResponse(
            success=False,
            smiles1=request.smiles1,
            smiles2=request.smiles2,
            tanimoto=None,
            error="RDKit not available",
        )

    score = _compute_tanimoto(request.smiles1, request.smiles2)
    if score is None:
        return TanimotoResponse(
            success=False,
            smiles1=request.smiles1,
            smiles2=request.smiles2,
            tanimoto=None,
            error="Failed to compute Tanimoto — check SMILES validity",
        )

    return TanimotoResponse(
        success=True,
        smiles1=request.smiles1,
        smiles2=request.smiles2,
        tanimoto=score,
        error=None,
    )


class BatchTanimotoRequest(BaseModel):
    target_smiles: str
    smiles_list: list[str]
    threshold: float = 0.7


class BatchTanimotoResponse(BaseModel):
    success: bool
    target_smiles: str
    results: list[dict]
    error: str | None = None


@router.post("/tanimoto/batch", response_model=BatchTanimotoResponse)
async def batch_tanimoto_similarity(
    request: BatchTanimotoRequest,
) -> BatchTanimotoResponse:
    if not _RDKI_AVAILABLE:
        return BatchTanimotoResponse(
            success=False,
            target_smiles=request.target_smiles,
            results=[],
            error="RDKit not available",
        )

    target = request.target_smiles
    target_mol = Chem.MolFromSmiles(target)
    if target_mol is None:
        return BatchTanimotoResponse(
            success=False,
            target_smiles=target,
            results=[],
            error="Invalid target SMILES",
        )

    target_fp = AllChem.GetMorganFingerprintAsBitVect(target_mol, 2, nBits=2048)
    results = []
    for smiles in request.smiles_list:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            continue
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
        score = float(target_fp.TanimotoSimilarity(fp))
        if score >= request.threshold:
            results.append({"smiles": smiles, "tanimoto": score})

    results.sort(key=lambda x: x["tanimoto"], reverse=True)
    return BatchTanimotoResponse(
        success=True,
        target_smiles=target,
        results=results,
        error=None,
    )
