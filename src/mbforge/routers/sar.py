"""SAR (Structure-Activity Relationship) endpoints — fail-closed stubs.

Real MCS / R-group decomposition is not implemented in Phase 0.
Return success:false so FE does not treat empty matrices as real results.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

_STUB_MSG = (
    "SAR analysis not implemented yet (Phase 0 stub). "
    "UI should show experimental/unavailable, not empty success."
)


@router.post("/find-scaffold")
async def find_scaffold(body: dict) -> dict:
    """Find common scaffold — not implemented."""
    return {
        "success": False,
        "error": _STUB_MSG,
        "scaffold": "",
        "smiles": body.get("smiles", body.get("smilesList", "")),
        "found": False,
    }


@router.post("/decompose")
async def decompose(body: dict) -> dict:
    """R-group decomposition — not implemented."""
    return {
        "success": False,
        "error": _STUB_MSG,
        "compound_id": "",
        "compound_name": "",
        "smiles": body.get("smiles", ""),
        "core_matches": False,
        "r_groups": [],
    }


@router.post("/build-matrix")
async def build_matrix(body: dict) -> dict:
    """Build R-group matrix — not implemented."""
    return {
        "success": False,
        "error": _STUB_MSG,
        "core_smiles": body.get("coreSmiles") or body.get("core_smiles") or "",
        "r_labels": [],
        "rows": [],
        "compounds": [],
        "unmatched_count": 0,
    }


@router.post("/heatmap")
async def heatmap(body: dict) -> list:
    """Activity heatmap — not implemented; empty list + no success flag.

    Callers must only invoke after a successful build-matrix. Returning an
    empty list (not a fake success envelope) keeps FE ``ActivityHeatmap[]``
    typing; build-matrix is the gate that fails closed.
    """
    _ = body
    return []
