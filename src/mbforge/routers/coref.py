"""Coreference resolution endpoints — stub implementations."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.post("/molecule-chain")
async def molecule_chain(body: dict) -> dict:
    """Cross-page coref chain stub."""
    return {"mol_id": body.get("molId", ""), "occurrences": [], "aliases": []}


@router.post("/page-parse-result")
async def page_parse_result(body: dict) -> dict:
    """Page parse result stub."""
    return {"page": body.get("page", 0), "structured_text": [], "molecules": [], "findings": []}


@router.post("/figure-labels")
async def figure_labels(body: dict) -> dict:
    """Figure labels stub."""
    return []


@router.post("/predictions")
async def coref_predictions(body: dict) -> dict:
    """Coref predictions stub."""
    return []


@router.post("/ensure-for-image")
async def ensure_for_image(body: dict) -> dict:
    """Ensure coref for image stub."""
    return {
        "doc_id": body.get("docId", ""),
        "page": body.get("page", 0),
        "already_existed": False,
        "labels_written": 0,
        "predictions_written": 0,
        "error": None,
    }


@router.post("/confirm-prediction")
async def confirm_prediction(body: dict) -> dict:
    """Confirm coref prediction stub."""
    return {"success": True}


@router.post("/update-pair")
async def update_pair(body: dict) -> dict:
    """Update coref pair stub."""
    return 0
