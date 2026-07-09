"""RapidOCR local backend (last-resort fallback).

Wraps the existing singleton at `mbforge.parsers.molecule.coref_alt.get_rapid_ocr`
as a uniform OCRBackend. Used by the chain only when all three cloud
backends fail (auth missing, quota exhausted, network down).

For PDF text extraction, RapidOCR was the previous default. The chain
now prefers cloud but still falls through to it so the pipeline never
silently drops text on scanned pages.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import OCRBackend, OCRResult

if TYPE_CHECKING:
    from mbforge.parsers.molecule.coref_alt import _RapidOCRAdapter

logger = logging.getLogger(__name__)


class RapidOCRBackend(OCRBackend):
    name = "rapidocr"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._adapter: _RapidOCRAdapter | None = None

    def _ensure_adapter(self) -> _RapidOCRAdapter:
        if self._adapter is None:
            from mbforge.parsers.molecule.coref_alt import get_rapid_ocr

            self._adapter = get_rapid_ocr()
        return self._adapter

    def is_configured(self) -> bool:
        """RapidOCR has no external config — always available if installed."""
        try:
            self._ensure_adapter()
            return True
        except Exception:  # noqa: BLE001
            return False

    def extract_text(self, image: bytes) -> OCRResult:
        """Run RapidOCR on a PNG byte buffer.

        Mirrors the call shape used by `extract_text.py::_ocr_pages`:
        decode PNG → numpy array → engine.run() → concat txts.
        """
        try:
            import io

            import numpy as np
            from PIL import Image

            adapter = self._ensure_adapter()
            pil_img = Image.open(io.BytesIO(image)).convert("RGB")
            arr = np.array(pil_img)
            out = adapter._engine(arr)  # type: ignore[attr-defined]
            if out and getattr(out, "txts", None):
                text = "\n".join(t for t in out.txts if t)
                return OCRResult(text=text)
            return OCRResult(text="", error="RapidOCR returned no text")
        except Exception as exc:  # noqa: BLE001
            logger.warning("RapidOCR failed: %s", exc)
            return OCRResult(text="", error=str(exc))
