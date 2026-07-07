"""OCR backends — cloud-first with local RapidOCR as last resort.

Default priority for PDF text extraction is set in `chain.DEFAULT_PRIORITY`:

    MinerU → PaddleOCR → GLM-OCR → RapidOCR
"""

from .base import OCRBackend, OCRResult
from .chain import (
    DEFAULT_PRIORITY,
    build_backends,
    extract_text_with_chain,
    list_configured_backends,
)
from .glmocr import GLMOCRBackend
from .local import RapidOCRBackend
from .mineru import MinerUBackend
from .paddleocr import PaddleOCRBackend

__all__ = [
    "OCRBackend",
    "OCRResult",
    "DEFAULT_PRIORITY",
    "MinerUBackend",
    "PaddleOCRBackend",
    "GLMOCRBackend",
    "RapidOCRBackend",
    "build_backends",
    "extract_text_with_chain",
    "list_configured_backends",
]
