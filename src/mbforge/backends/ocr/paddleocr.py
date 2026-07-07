"""PaddleOCR cloud backend (Baidu AI Studio hosted).

PaddleOCR's hosted endpoint accepts a multipart file upload and returns
JSON containing `words_result` (a list of {words, confidence, location}
records). We extract `words` from each item and join with newlines.

For images: standard OCR. For PDFs: PaddleOCR's service handles them
on its side; we just send the bytes through.
"""

from __future__ import annotations

import logging

import httpx

from .base import OCRBackend, OCRResult

logger = logging.getLogger(__name__)

DEFAULT_HOST = "https://aistudio.baidu.com"
OCR_ENDPOINT_TMPL = "/paddleocr/api/ocr/{model}"


class PaddleOCRBackend(OCRBackend):
    name = "paddleocr"

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}
        self.api_key: str = (cfg.get("api_key") or "").strip()
        self.host: str = (cfg.get("host") or "").strip() or DEFAULT_HOST
        self.model: str = (cfg.get("model") or "PaddleOCR-VL-1.6").strip() or "PaddleOCR-VL-1.6"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def extract_text(self, image: bytes) -> OCRResult:
        if not self.is_configured():
            return OCRResult(text="", error="PaddleOCR api_key not set")
        endpoint = f"{self.host.rstrip('/')}{OCR_ENDPOINT_TMPL.format(model=self.model)}"
        try:
            with httpx.Client(timeout=60) as client:
                r = client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"file": ("page.png", image, "image/png")},
                )
                r.raise_for_status()
                payload = r.json()
            text = self._extract_text(payload)
            return OCRResult(text=text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PaddleOCR OCR failed: %s", exc)
            return OCRResult(text="", error=str(exc))

    @staticmethod
    def _extract_text(payload: dict) -> str:
        """Tolerate multiple response shapes across PaddleOCR versions."""
        # Shape A: {"words_result": [{"words": "...", "confidence": ...}]}
        words = payload.get("words_result")
        if isinstance(words, list):
            return "\n".join(
                item.get("words", "")
                for item in words
                if isinstance(item, dict)
            )
        # Shape B: {"result": [{"text": "...", "score": ...}]}
        result = payload.get("result")
        if isinstance(result, list):
            return "\n".join(
                item.get("text", "")
                for item in result
                if isinstance(item, dict)
            )
        # Shape C: {"text": "..."}
        if isinstance(payload.get("text"), str):
            return payload["text"]
        return ""
