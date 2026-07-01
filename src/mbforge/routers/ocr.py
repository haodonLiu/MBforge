"""OCR testing endpoints — stub implementations."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.post("/test-mineru")
async def test_mineru(body: dict) -> dict:
    """Test MinerU connection stub."""
    return {"ok": False, "status": None, "message": "OCR test not available in web mode"}


@router.post("/test-uniparser")
async def test_uniparser(body: dict) -> dict:
    """Test Uniparser connection stub."""
    return {"ok": False, "status": None, "message": "OCR test not available in web mode"}


@router.post("/test-paddleocr")
async def test_paddleocr(body: dict) -> dict:
    """Test PaddleOCR connection stub."""
    return {"ok": False, "status": None, "message": "OCR test not available in web mode"}
