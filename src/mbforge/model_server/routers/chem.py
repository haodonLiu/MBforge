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

    _RDKIT_AVAILABLE = True
except ImportError:
    _RDKIT_AVAILABLE = False


class TanimotoRequest(BaseModel):
    esmiles1: str
    esmiles2: str


class TanimotoResponse(BaseModel):
    success: bool
    esmiles1: str
    esmiles2: str
    tanimoto: float | None
    error: str | None = None


def _compute_tanimoto(s1: str, s2: str) -> float | None:
    if not _RDKIT_AVAILABLE:
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
    try:
        if not _RDKIT_AVAILABLE:
            return TanimotoResponse(
                success=False,
                esmiles1=request.esmiles1,
                esmiles2=request.esmiles2,
                tanimoto=None,
                error="RDKit not available",
            )

        score = _compute_tanimoto(request.esmiles1, request.esmiles2)
        if score is None:
            return TanimotoResponse(
                success=False,
                esmiles1=request.esmiles1,
                esmiles2=request.esmiles2,
                tanimoto=None,
                error="Failed to compute Tanimoto — check E-SMILES validity",
            )

        return TanimotoResponse(
            success=True,
            esmiles1=request.esmiles1,
            esmiles2=request.esmiles2,
            tanimoto=score,
            error=None,
        )
    except Exception as e:
        logger.error(f"Tanimoto failed for {request.esmiles1} vs {request.esmiles2}: {e}", exc_info=True)
        return TanimotoResponse(
            success=False,
            esmiles1=request.esmiles1,
            esmiles2=request.esmiles2,
            tanimoto=None,
            error=str(e),
        )


class BatchTanimotoRequest(BaseModel):
    target_esmiles: str
    esmiles_list: list[str]
    threshold: float = 0.7


class BatchTanimotoResponse(BaseModel):
    success: bool
    target_esmiles: str
    results: list[dict]
    error: str | None = None


@router.post("/tanimoto/batch", response_model=BatchTanimotoResponse)
async def batch_tanimoto_similarity(
    request: BatchTanimotoRequest,
) -> BatchTanimotoResponse:
    try:
        if not _RDKIT_AVAILABLE:
            return BatchTanimotoResponse(
                success=False,
                target_esmiles=request.target_esmiles,
                results=[],
                error="RDKit not available",
            )

        target = request.target_esmiles
        target_mol = Chem.MolFromSmiles(target)
        if target_mol is None:
            return BatchTanimotoResponse(
                success=False,
                target_esmiles=target,
                results=[],
                error="Invalid target E-SMILES",
            )

        target_fp = AllChem.GetMorganFingerprintAsBitVect(target_mol, 2, nBits=2048)
        results = []
        for esmiles_str in request.esmiles_list:
            mol = Chem.MolFromSmiles(esmiles_str)
            if mol is None:
                continue
            fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
            score = float(target_fp.TanimotoSimilarity(fp))
            if score >= request.threshold:
                results.append({"esmiles": esmiles_str, "tanimoto": score})

        results.sort(key=lambda x: x["tanimoto"], reverse=True)
        return BatchTanimotoResponse(
            success=True,
            target_esmiles=target,
            results=results,
            error=None,
        )
    except Exception as e:
        logger.error(f"Batch Tanimoto failed target={request.target_esmiles}: {e}", exc_info=True)
        return BatchTanimotoResponse(
            success=False,
            target_esmiles=request.target_esmiles,
            results=[],
            error=str(e),
        )


# ============================================================================
# 结构校验（用于 OCR 矫正后实时反馈）
# ============================================================================

from pydantic import Field  # noqa: E402  # 追加位置可保持紧凑


class ValidateRequest(BaseModel):
    """单条 SMILES 结构校验请求."""

    esmiles: str = Field(..., min_length=1, max_length=2000, description="待校验的 E-SMILES")


class ValidateResponse(BaseModel):
    """结构校验结果.

    Attributes:
        valid: 解析是否成功（基本结构 OK）
        canonical_smiles: 规范化后的 SMILES（去除 E-SMILES 标签、立体化学校验后的标准形式）
        issues: 发现的问题列表（每项含 code + message + severity）
        error: 系统级错误（与 issues 不同：RDKit 不可用等）
    """

    success: bool
    esmiles: str
    valid: bool = False
    canonical_smiles: str | None = None
    issues: list[dict] = Field(default_factory=list)
    error: str | None = None


def _strip_esmiles_tags_local(s: str) -> str:
    """剥离 E-SMILES 语义标签 (<c>1:R1</c> 等)."""
    import re
    return re.sub(r"<[a-zA-Z]>\d+:[^<]+</[a-zA-Z]>", "", s)


def _validate_smiles(esmiles: str) -> dict:
    """实际的结构校验逻辑."""
    if not _RDKIT_AVAILABLE:
        return {
            "valid": False,
            "canonical_smiles": None,
            "issues": [{"code": "RDKIT_UNAVAILABLE", "message": "RDKit 不可用", "severity": "error"}],
        }

    issues: list[dict] = []
    cleaned = _strip_esmiles_tags_local(esmiles)

    try:
        mol = Chem.MolFromSmiles(cleaned)
    except Exception as e:
        return {
            "valid": False,
            "canonical_smiles": None,
            "issues": [{"code": "PARSE_EXCEPTION", "message": str(e), "severity": "error"}],
        }

    if mol is None:
        return {
            "valid": False,
            "canonical_smiles": None,
            "issues": [{
                "code": "PARSE_FAILED",
                "message": "RDKit 无法解析该 SMILES（语法错误或未知元素）",
                "severity": "error",
            }],
        }

    # 规范化
    try:
        canonical = Chem.MolToSmiles(mol, canonical=True)
    except Exception as e:
        issues.append({
            "code": "CANONICALIZE_FAILED",
            "message": f"规范化失败: {e}",
            "severity": "warning",
        })
        canonical = cleaned

    # 价态/芳香性检查
    try:
        Chem.Kekulize(mol)
    except Exception as e:
        issues.append({
            "code": "KEKULIZE_FAILED",
            "message": f"Kekulize 失败（芳香环解析异常）: {e}",
            "severity": "warning",
        })

    n_heavy = mol.GetNumHeavyAtoms()
    if n_heavy == 0:
        issues.append({
            "code": "EMPTY_MOLECULE",
            "message": "分子中没有重原子",
            "severity": "error",
        })
    if n_heavy > 200:
        issues.append({
            "code": "UNUSUALLY_LARGE",
            "message": f"分子过大（{n_heavy} 重原子），请检查结构",
            "severity": "warning",
        })

    return {
        "valid": not any(i["severity"] == "error" for i in issues),
        "canonical_smiles": canonical,
        "issues": issues,
    }


@router.post("/validate", response_model=ValidateResponse)
async def validate_smiles(request: ValidateRequest) -> ValidateResponse:
    """校验单条 SMILES 结构.

    用于 OCR 矫正流程：用户手动编辑 SMILES 后实时校验.
    """
    try:
        result = _validate_smiles(request.esmiles)
        return ValidateResponse(
            success=True,
            esmiles=request.esmiles,
            valid=result["valid"],
            canonical_smiles=result["canonical_smiles"],
            issues=result["issues"],
            error=None,
        )
    except Exception as e:
        logger.error(f"validate failed for {request.esmiles}: {e}", exc_info=True)
        return ValidateResponse(
            success=False,
            esmiles=request.esmiles,
            valid=False,
            canonical_smiles=None,
            issues=[],
            error=str(e),
        )


# ============================================================================
# 批量结构校验（用于文档提取后批量验证）
# ============================================================================


class BatchValidateRequest(BaseModel):
    """批量 SMILES 结构校验请求."""

    esmiles_list: list[str] = Field(..., min_length=1, max_length=200, description="待校验的 E-SMILES 列表")


class BatchValidateResponse(BaseModel):
    """批量校验结果.

    Attributes:
        success: 是否成功处理（单条失败不影响整体 success）
        results: 每条校验结果列表（顺序与请求一致）
        error: 系统级错误
    """

    success: bool
    results: list[dict] = Field(default_factory=list)
    error: str | None = None


@router.post("/validate/batch", response_model=BatchValidateResponse)
async def batch_validate_smiles(request: BatchValidateRequest) -> BatchValidateResponse:
    """批量校验 SMILES 结构.

    用于文档提取管线：一次性验证 LLM 提取出的多个化合物结构。
    """
    try:
        results = []
        for esmiles in request.esmiles_list:
            result = _validate_smiles(esmiles)
            results.append(
                {
                    "esmiles": esmiles,
                    "valid": result["valid"],
                    "canonical_smiles": result["canonical_smiles"],
                    "issues": result["issues"],
                }
            )
        return BatchValidateResponse(success=True, results=results, error=None)
    except Exception as e:
        logger.error(f"Batch validate failed: {e}", exc_info=True)
        return BatchValidateResponse(success=False, results=[], error=str(e))


# ============================================================================
# 指纹计算 + 子结构搜索
# ============================================================================


class FingerprintRequest(BaseModel):
    """计算 Morgan 指纹."""

    esmiles: str


class FingerprintResponse(BaseModel):
    success: bool
    fingerprint: str | None = None  # base64 编码的 2048-bit Morgan 指纹
    error: str | None = None


@router.post("/fingerprint", response_model=FingerprintResponse)
async def compute_fingerprint(request: FingerprintRequest) -> FingerprintResponse:
    """计算单个分子的 Morgan 指纹 (radius=2, nbits=2048)."""
    try:
        if not _RDKIT_AVAILABLE:
            return FingerprintResponse(success=False, error="RDKit not available")

        mol = Chem.MolFromSmiles(request.esmiles)
        if mol is None:
            return FingerprintResponse(success=False, error="Invalid SMILES")

        fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
        import base64

        fp_bytes = fp.ToBitString().encode("ascii")
        # 将 bit string 转为 bytes（每 8 bit 一个 byte）
        fp_bytes_packed = bytes(
            int(fp_bytes[i : i + 8], 2) for i in range(0, len(fp_bytes), 8)
        )
        fp_b64 = base64.b64encode(fp_bytes_packed).decode("ascii")
        return FingerprintResponse(success=True, fingerprint=fp_b64)
    except Exception as e:
        logger.error(f"Fingerprint failed for {request.esmiles}: {e}", exc_info=True)
        return FingerprintResponse(success=False, error=str(e))


class FingerprintBatchRequest(BaseModel):
    """批量计算 Morgan 指纹."""

    esmiles_list: list[str]


class FingerprintBatchResponse(BaseModel):
    success: bool
    fingerprints: list[str | None] = Field(default_factory=list)
    error: str | None = None


@router.post("/fingerprint/batch", response_model=FingerprintBatchResponse)
async def batch_fingerprint(request: FingerprintBatchRequest) -> FingerprintBatchResponse:
    """批量计算 Morgan 指纹."""
    try:
        if not _RDKIT_AVAILABLE:
            return FingerprintBatchResponse(success=False, error="RDKit not available")

        import base64

        results = []
        for esmiles in request.esmiles_list:
            mol = Chem.MolFromSmiles(esmiles)
            if mol is None:
                results.append(None)
                continue
            fp = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)
            fp_bytes = fp.ToBitString().encode("ascii")
            fp_bytes_packed = bytes(
                int(fp_bytes[i : i + 8], 2) for i in range(0, len(fp_bytes), 8)
            )
            results.append(base64.b64encode(fp_bytes_packed).decode("ascii"))
        return FingerprintBatchResponse(success=True, fingerprints=results)
    except Exception as e:
        logger.error(f"Batch fingerprint failed: {e}", exc_info=True)
        return FingerprintBatchResponse(success=False, error=str(e))


class SubstructureSearchRequest(BaseModel):
    """子结构搜索请求."""

    query_smiles: str
    candidate_esmiles: list[str]


class SubstructureSearchResponse(BaseModel):
    success: bool
    matches: list[str] = Field(default_factory=list)  # 匹配的 SMILES 列表
    error: str | None = None


@router.post("/substructure_search", response_model=SubstructureSearchResponse)
async def substructure_search(
    request: SubstructureSearchRequest,
) -> SubstructureSearchResponse:
    """对候选分子列表执行子结构搜索（RDKit HasSubstructMatch）."""
    try:
        if not _RDKIT_AVAILABLE:
            return SubstructureSearchResponse(success=False, error="RDKit not available")

        query_mol = Chem.MolFromSmiles(request.query_smiles)
        if query_mol is None:
            return SubstructureSearchResponse(
                success=False, error="Invalid query SMILES"
            )

        matches = []
        for esmiles in request.candidate_esmiles:
            mol = Chem.MolFromSmiles(esmiles)
            if mol is None:
                continue
            if mol.HasSubstructMatch(query_mol):
                matches.append(esmiles)

        return SubstructureSearchResponse(success=True, matches=matches)
    except Exception as e:
        logger.error(f"Substructure search failed: {e}", exc_info=True)
        return SubstructureSearchResponse(success=False, error=str(e))
