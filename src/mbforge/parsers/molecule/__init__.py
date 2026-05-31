"""分子提取与解析子包."""

from __future__ import annotations

from .coords import image_to_pdf_bbox, pdf_to_image_bbox, scale_from_page_size
from .extraction_result import ExtractionResult
from .mol_image_pipeline import (
    MolDetv2DocDetector,
    MolDetv2GeneralDetector,
    MolImagePipeline,
    MolScribeRecognizer,
)
from .molscribe import MolScribe as _MolScribeAlias
from .molscribe import MolScribeConfig, MolScribeResult

# Convenience re-export
MolScribe = _MolScribeAlias

__all__ = [
    "ExtractionResult",
    "MolDetv2DocDetector",
    "MolDetv2GeneralDetector",
    "MolImagePipeline",
    "MolScribe",
    "MolScribeConfig",
    "MolScribeRecognizer",
    "MolScribeResult",
    "image_to_pdf_bbox",
    "pdf_to_image_bbox",
    "scale_from_page_size",
]
