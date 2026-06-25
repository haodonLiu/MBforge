"""MolScribe backend — chemical structure image → E-SMILES."""

from __future__ import annotations

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
    """Lazy-load MolScribe model.

    只读盘：若 `~/mbforge/models/MolScribe/` 下没有 checkpoint 或 safetensors，
    标记为不可用，**不触发任何下载**。
    """
    global _MODEL, _AVAILABLE, _ERROR
    if _MODEL is not None:
        return
    try:
        from ..core.resource_manager import ResourceManager
        from ..parsers.molecule.molscribe_inference import (
            MolScribe as _MolScribeBackend,
        )

        path = ResourceManager.get_molscribe_path()
        if path is None:
            _AVAILABLE = False
            _ERROR = "MolScribe 模型未找到（请在 ~/mbforge/models/MolScribe/ 放置模型文件，或在设置中下载）"
            logger.warning(_ERROR)
            return

        dev = device or ("cuda" if is_gpu_available() else "cpu")
        _MODEL = _MolScribeBackend(str(path), device=dev, num_workers=1)
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
        return ExtractionResult(
            esmiles="",
            scribe_conf=0.0,
            properties={"error": _ERROR or "model not available"},
        )
    try:
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)
        raw = _MODEL.predict_images([image])[0]
        smiles = raw.get("smiles", "") or ""
        conf = float(raw.get("confidence", 0.0))
        return ExtractionResult(
            esmiles=smiles,
            scribe_conf=conf,
            properties={"molfile": raw.get("molfile", "")},
        )
    except Exception as exc:
        logger.warning("MolScribe predict failed: %s", exc)
        return ExtractionResult(
            esmiles="",
            scribe_conf=0.0,
            properties={"error": str(exc)},
        )


def predict_batch(images: list[Image.Image | np.ndarray]) -> list[ExtractionResult]:
    """Predict batch of images.

    Accepts a mix of PIL `Image.Image` and `numpy.ndarray` (uint8 HxWxC or HxW).
    Each entry is forwarded to `predict` after the array→PIL normalization
    performed there, so callers do not need to pre-convert.
    """
    return [predict(img) for img in images]
