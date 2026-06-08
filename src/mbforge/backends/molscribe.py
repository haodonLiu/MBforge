"""MolScribe backend — chemical structure image → E-SMILES."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from ..parsers.molecule.extraction_result import ExtractionResult
from ..utils.helpers import is_gpu_available
from ..utils.logger import get_logger

logger = get_logger(__name__)

_MODEL = None
_AVAILABLE: bool = False
_ERROR: str = ""


def load(device: str | None = None) -> None:
    """Lazy-load MolScribe model."""
    global _MODEL, _AVAILABLE, _ERROR
    if _MODEL is not None:
        return
    try:
        from ..parsers.molecule.molscribe_inference import MolScribe as _MolScribeBackend
        from ..parsers.molecule.molscribe_inference.download import ensure_molscribe_model
        from ..core.resource_manager import ResourceManager

        ckpt = None
        try:
            path = ResourceManager.get_molscribe_path()
            if path is not None:
                ckpt = str(path)
        except Exception:
            pass
        if ckpt is None:
            ckpt = ensure_molscribe_model()

        dev = device or ("cuda" if is_gpu_available() else "cpu")
        _MODEL = _MolScribeBackend(str(ckpt), device=dev, num_workers=1)
        _AVAILABLE = True
        logger.info("MolScribe loaded successfully")
    except Exception as exc:
        _ERROR = str(exc)
        _AVAILABLE = False
        logger.error("MolScribe load failed: %s", exc)


def unload() -> None:
    """Release model."""
    global _MODEL, _AVAILABLE, _ERROR
    _MODEL = None
    _AVAILABLE = False
    _ERROR = ""


def health() -> dict[str, str]:
    return {
        "status": "ready" if _AVAILABLE else ("error" if _ERROR else "loading"),
        "error": _ERROR,
    }


def predict(image: Image.Image | np.ndarray) -> ExtractionResult:
    """Predict single image."""
    if not _AVAILABLE or _MODEL is None:
        return ExtractionResult("", 0.0, success=False, error=_ERROR or "model not available")
    try:
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)
        raw = _MODEL.predict_images([image])[0]
        smiles = raw.get("smiles", "")
        conf = raw.get("confidence", 0.5)
        return ExtractionResult(
            esmiles=smiles,
            confidence=float(conf),
            molfile=raw.get("molfile", ""),
        )
    except Exception as exc:
        logger.warning("MolScribe predict failed: %s", exc)
        return ExtractionResult("", 0.0, success=False, error=str(exc))


def predict_batch(images: list) -> list[ExtractionResult]:
    """Predict batch of images."""
    return [predict(img) for img in images]
