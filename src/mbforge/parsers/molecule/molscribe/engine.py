from __future__ import annotations

import numpy as np
from PIL import Image

from .config import MolScribeConfig
from .result import MolScribeResult
from mbforge.utils.logger import get_logger

logger = get_logger(__name__)


class MolScribeEngine:
    """Low-level wrapper around molscribe_inference."""

    def __init__(self, config: MolScribeConfig) -> None:
        self.config = config
        self._model = None
        self._load()

    def _resolve_device(self) -> str | None:
        if self.config.device in ("auto", ""):
            return None
        return self.config.device

    def _load(self) -> None:
        from ..molscribe_inference import MolScribe as _MolScribe
        from ..molscribe_inference.download import ensure_molscribe_model

        ckpt = self.config.model_path
        if ckpt is None:
            ckpt = ensure_molscribe_model()

        self._model = _MolScribe(
            str(ckpt), device=self._resolve_device(),
            num_workers=self.config.num_workers,
        )

    def is_loaded(self) -> bool:
        return self._model is not None

    def predict(self, image: Image.Image | np.ndarray) -> MolScribeResult:
        if not self.is_loaded():
            return MolScribeResult("", 0.0, success=False, error="model not loaded")
        try:
            if isinstance(image, np.ndarray):
                image = Image.fromarray(image)
            raw = self._model.predict_images([image])[0]
            smiles = raw.get("smiles", "")
            conf = raw.get("confidence", 0.5)
            if self.config.log_smiles:
                logger.info("MolScribe: %s (conf=%.3f)", smiles, conf)
            return MolScribeResult(
                esmiles=smiles,
                confidence=float(conf),
                molfile=raw.get("molfile", ""),
            )
        except Exception as exc:
            logger.warning("MolScribe predict failed: %s", exc)
            return MolScribeResult("", 0.0, success=False, error=str(exc))

    def predict_batch(self, images: list) -> list[MolScribeResult]:
        return [self.predict(img) for img in images]
