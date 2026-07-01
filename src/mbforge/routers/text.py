"""Text processing, classification, and extraction endpoints — stub implementations."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.post("/text/chunk")
async def text_chunk(body: dict) -> dict:
    """Text chunking stub."""
    text = body.get("text", "")
    return {"chunks": [text] if text else [], "total_chunks": 1 if text else 0}


@router.post("/classify/page")
async def classify_page(body: dict) -> dict:
    """Page classification stub."""
    return {
        "page_idx": body.get("pageIdx", 0),
        "text_density": 0.0,
        "is_scanned": False,
        "has_molecular_patterns": False,
    }


@router.post("/classify/document")
async def classify_document(body: dict) -> dict:
    """Document classification stub."""
    return {
        "text_density": 0.0,
        "is_scanned": False,
        "has_molecular_patterns": False,
        "metadata_hints": None,
        "pages": [],
        "needs_confirmation": False,
    }


@router.post("/extract/esmiles-candidates")
async def extract_esmiles_candidates(body: dict) -> dict:
    """Extract E-SMILES candidates stub."""
    return []


@router.post("/extract/activities")
async def extract_activities(body: dict) -> dict:
    """Extract activities stub."""
    return []


@router.post("/extract/associated-molecules")
async def extract_associated_molecules(body: dict) -> dict:
    """Extract associated molecules stub."""
    return []
