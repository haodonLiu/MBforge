"""RapidOCR local backend (last-resort fallback).

Wraps the shared singleton at `mbforge.backends.ocr.rapidocr_adapter.RapidOCRCropAdapter`
as a uniform OCRBackend. Used by the chain only when all three cloud
backends fail (auth missing, quota exhausted, network down).

For PDF text extraction, RapidOCR was the previous default. The chain
now prefers cloud but still falls through to it so the pipeline never
silently drops text on scanned pages.
"""

from __future__ import annotations

import io
import logging

from PIL import Image

from .base import OCRBackend, OCRResult
from .rapidocr_adapter import RapidOCRCropAdapter

logger = logging.getLogger(__name__)


class RapidOCRBackend(OCRBackend):
    name = "rapidocr"

    def is_configured(self) -> bool:
        """RapidOCR has no external config — available if rapidocr is installed."""
        try:
            RapidOCRCropAdapter.instance()
            return True
        except Exception:  # noqa: BLE001
            return False

    def extract_text(self, image: bytes) -> OCRResult:
        """Run RapidOCR on a PNG byte buffer.

        Decodes the PNG, runs full-page detection + recognition through the
        shared ``RapidOCRCropAdapter`` singleton, and returns the concatenated
        text.
        """
        try:
            adapter = RapidOCRCropAdapter.instance()
            pil_img = Image.open(io.BytesIO(image)).convert("RGB")
            text = adapter.readtext_page(pil_img)
            return OCRResult(text=text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RapidOCR failed: %s", exc)
            return OCRResult(text="", error=str(exc))
