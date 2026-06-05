"""SAR (Structure-Activity Relationship) 分析路由.

端点:
- POST /api/v1/sar/scaffold       共同骨架提取
- POST /api/v1/sar/matrix         构建 R-group 矩阵
- POST /api/v1/sar/heatmap        活性热力图
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...csar.sar import (
    build_activity_heatmap,
    build_rgroup_matrix,
    find_common_scaffold,
    is_available,
)
from ...utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ScaffoldRequest(BaseModel):
    """共同骨架提取请求."""

    smiles_list: list[str] = Field(..., min_length=2, description="化合物 SMILES 列表")
    timeout: float = Field(
        default=5.0, ge=0.5, le=30.0, description="MCS 搜索超时（秒）"
    )
    min_atoms: int = Field(default=3, ge=1, le=50, description="骨架最少原子数")


class ScaffoldResponse(BaseModel):
    success: bool
    core_smiles: str | None = None
    num_input: int = 0
    error: str | None = None


class CompoundInput(BaseModel):
    """矩阵输入的单个化合物."""

    id: str = ""
    name: str = ""
    smiles: str
    activity: float | None = None
    activity_type: str | None = None
    units: str | None = None


class MatrixRequest(BaseModel):
    """R-group 矩阵构建请求."""

    compounds: list[CompoundInput] = Field(..., min_length=1)
    core_smiles: str | None = Field(
        default=None, description="已知骨架；为空时自动提取"
    )
    auto_extract_scaffold: bool = True
    mcs_timeout: float = 5.0


class MatrixResponse(BaseModel):
    success: bool
    core_smiles: str = ""
    r_labels: list[str] = []
    rows: list[list[str]] = []
    compounds: list[dict[str, Any]] = []
    unmatched_count: int = 0
    error: str | None = None


class HeatmapRequest(BaseModel):
    """热力图请求（matrix + lower_is_better）."""

    matrix: dict[str, Any]
    lower_is_better: bool = True


class HeatmapResponse(BaseModel):
    success: bool
    heatmaps: list[dict[str, Any]] = []
    error: str | None = None


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _matrix_from_dict(d: dict[str, Any]):
    """将请求里的 matrix dict 还原为 RGroupMatrix 兼容结构（duck-typed）."""

    # 复用 build_activity_heatmap，仅需 core_smiles/r_labels/rows/compounds 字段
    class _M:
        pass

    m = _M()
    m.core_smiles = d.get("core_smiles", "")
    m.r_labels = d.get("r_labels", [])
    m.rows = d.get("rows", [])
    m.compounds = d.get("compounds", [])
    return m


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.post("/scaffold", response_model=ScaffoldResponse)
async def extract_scaffold(request: ScaffoldRequest) -> ScaffoldResponse:
    """从 SMILES 列表中提取最大公共子结构 (MCS) 作为共同骨架."""
    if not is_available():
        return ScaffoldResponse(
            success=False,
            num_input=len(request.smiles_list),
            error="RDKit not available",
        )
    try:
        core = find_common_scaffold(
            request.smiles_list,
            timeout=request.timeout,
            min_atoms=request.min_atoms,
        )
        return ScaffoldResponse(
            success=core is not None,
            core_smiles=core,
            num_input=len(request.smiles_list),
            error=None
            if core
            else "No common scaffold found (MCS returned empty or too small)",
        )
    except Exception as e:
        logger.error(f"scaffold extraction failed: {e}", exc_info=True)
        return ScaffoldResponse(
            success=False,
            num_input=len(request.smiles_list),
            error=str(e),
        )


@router.post("/matrix", response_model=MatrixResponse)
async def build_matrix(request: MatrixRequest) -> MatrixResponse:
    """构建 R-group 矩阵."""
    if not is_available():
        return MatrixResponse(
            success=False,
            error="RDKit not available",
        )
    try:
        compounds_data = [c.model_dump() for c in request.compounds]
        matrix = build_rgroup_matrix(
            compounds=compounds_data,
            core_smiles=request.core_smiles,
            auto_extract_scaffold=request.auto_extract_scaffold,
            mcs_timeout=request.mcs_timeout,
        )
        return MatrixResponse(
            success=True,
            core_smiles=matrix.core_smiles,
            r_labels=matrix.r_labels,
            rows=matrix.rows,
            compounds=matrix.compounds,
            unmatched_count=matrix.unmatched_count,
        )
    except Exception as e:
        logger.error(f"matrix build failed: {e}", exc_info=True)
        return MatrixResponse(success=False, error=str(e))


@router.post("/heatmap", response_model=HeatmapResponse)
async def get_heatmap(request: HeatmapRequest) -> HeatmapResponse:
    """基于 R-group 矩阵生成活性热力图."""
    if not is_available():
        return HeatmapResponse(success=False, error="RDKit not available")
    try:
        m = _matrix_from_dict(request.matrix)
        heatmaps = build_activity_heatmap(m, lower_is_better=request.lower_is_better)
        out = [
            {
                "r_label": h.r_label,
                "cells": h.cells,
            }
            for h in heatmaps
        ]
        return HeatmapResponse(success=True, heatmaps=out)
    except Exception as e:
        logger.error(f"heatmap build failed: {e}", exc_info=True)
        return HeatmapResponse(success=False, error=str(e))
