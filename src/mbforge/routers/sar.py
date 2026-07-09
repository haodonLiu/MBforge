"""SAR (Structure-Activity Relationship) endpoints — stub implementations."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.post("/find-scaffold")
async def find_scaffold(body: dict) -> dict:
    """Find common scaffold stub."""
    return {
        "scaffold": "",
        "smiles": body.get("smiles", ""),
        "found": False,
    }


@router.post("/decompose")
async def decompose(body: dict) -> dict:
    """R-group decomposition stub."""
    return {
        "compound_id": "",
        "compound_name": "",
        "smiles": body.get("smiles", ""),
        "core_matches": False,
        "r_groups": [],
    }


@router.post("/build-matrix")
async def build_matrix(body: dict) -> dict:
    """Build R-group matrix stub."""
    return {
        "core_smiles": body.get("coreSmiles", ""),
        "r_labels": [],
        "rows": [],
        "compounds": [],
        "unmatched_count": 0,
    }


@router.post("/heatmap")
async def heatmap(body: dict) -> dict:
    """Activity heatmap stub."""
    return []
