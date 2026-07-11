"""OCR fallback chain.

Default priority for PDF text extraction:

    MinerU → PaddleOCR → GLM-OCR → RapidOCR (local last resort)

Each backend in turn is asked to OCR the page. The first one that returns
non-empty text wins. If every backend fails or returns empty, the chain
returns empty (matching the historical RapidOCR-only behavior on failure).

`load_chain()` builds the chain from the live AppConfig.ocr dict so
changes to settings.json take effect on the next call.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from .base import OCRBackend, OCRResult
from .glmocr import GLMOCRBackend
from .local import RapidOCRBackend
from .mineru import MinerUBackend
from .paddleocr import PaddleOCRBackend

logger = logging.getLogger(__name__)

DEFAULT_PRIORITY: tuple[str, ...] = ("mineru", "paddleocr", "glmocr", "rapidocr")


def build_backends(ocr_config: dict | None) -> list[OCRBackend]:
    """Build backends in priority order from config.

    Backends that aren't configured (no api_key etc.) are silently
    dropped so the chain doesn't try them.
    """
    cfg = ocr_config or {}
    minersu_cfg = {
        "api_key": cfg.get("mineru_api_key") or cfg.get("api_key") or "",
        "base_url": cfg.get("base_url", ""),
        "model_version": cfg.get("model_version", "vlm"),
    }
    paddle_cfg = {
        "api_key": cfg.get("paddleocr_api_key", ""),
        "host": cfg.get("paddleocr_host", ""),
        "model": cfg.get("paddleocr_model", "PaddleOCR-VL-1.6"),
    }
    glm_cfg = {
        "api_key": cfg.get("glmocr_api_key") or cfg.get("api_key") or "",
        "base_url": cfg.get("glmocr_base_url") or cfg.get("base_url") or "",
        "model": cfg.get("glmocr_model", "glm-ocr"),
    }

    candidates: list[OCRBackend] = [
        MinerUBackend(minersu_cfg),
        PaddleOCRBackend(paddle_cfg),
        GLMOCRBackend(glm_cfg),
        RapidOCRBackend({}),
    ]
    return [b for b in candidates if b.is_configured()]


def extract_text_with_chain(image: bytes, ocr_config: dict | None) -> OCRResult:
    """Run OCR through the fallback chain. Returns the first non-empty result."""
    backends = build_backends(ocr_config)
    if not backends:
        return OCRResult(text="", error="no OCR backend configured")
    last_error: str | None = None
    for backend in backends:
        result = backend.extract_text(image)
        if result.text.strip():
            logger.info(
                "OCR chain succeeded with backend=%s after %d attempt(s)",
                backend.name,
                backends.index(backend) + 1,
            )
            return result
        last_error = result.error or f"{backend.name} returned empty"
    logger.warning("OCR chain exhausted without text: %s", last_error)
    return OCRResult(text="", error=last_error or "all backends returned empty")


def list_configured_backends(ocr_config: dict | None) -> Iterable[str]:
    """Names of backends that would participate in the chain."""
    return [b.name for b in build_backends(ocr_config)]
