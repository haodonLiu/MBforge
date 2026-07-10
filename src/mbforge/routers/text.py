"""Text processing, classification, and extraction endpoints.

Most endpoints in this router are thin stubs that the pipeline runs
in-process; the only endpoint that performs real work is
``/extract/activities``, which is wired to the on-demand
``extract_activities_from_document`` LLM table parser.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..utils.logger import get_logger

router = APIRouter()

logger = get_logger("mbforge.routers.text")


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
async def extract_activities(body: dict) -> list[dict]:
    """Extract activities from text using LLM-backed table parser.

    The pipeline runs the same parser in-process during the
    ``extract_activities`` stage; this endpoint lets the front-end
    trigger an on-demand parse for the SAR panel preview. Failures
    degrade to an empty list so the caller never sees a 500 from a
    missing LLM key or a malformed table.
    """
    text = body.get("text", "")
    if not text:
        return []
    try:
        from ..pipeline.extract_activities import (
            _extract_tables_from_markdown,
            _parse_table_with_llm,
        )

        tables = _extract_tables_from_markdown(text)
        if not tables:
            return []
        results: list[dict] = []
        for table_md, _page_num in tables[:5]:  # Phase 0: cap at first 5 tables
            try:
                records = _parse_table_with_llm(
                    table_md, 0, model="gpt-4o-mini", page_num=None
                )
            except Exception as exc:
                logger.warning("Table parse failed: %s", exc)
                continue
            for rec in records:
                results.append(
                    {
                        "activity_type": rec.activity_type,
                        "value": rec.value,
                        "units": rec.unit,
                        "context": rec.raw_text,
                    }
                )
        return results
    except Exception as exc:
        logger.error("Activity extraction failed: %s", exc)
        return []


@router.post("/extract/associated-molecules")
async def extract_associated_molecules(body: dict) -> dict:
    """Extract associated molecules stub."""
    return []
