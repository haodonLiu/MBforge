"""MolScribe: chemical structure image → E-SMILES.

Standalone callable module. Usage::

    from mbforge.parsers.molecule.molscribe import MolScribe, MolScribeConfig

    model = MolScribe()
    result = model.predict(image)
    print(result.esmiles, result.confidence)

    # override config
    cfg = MolScribeConfig(device="cuda:0", batch_size=32)
    model = MolScribe(cfg)
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from .config import MolScribeConfig
from .result import MolScribeResult
from .engine import MolScribeEngine
from mbforge.utils.helpers import is_gpu_available
from mbforge.utils.logger import get_logger

logger = get_logger(__name__)


class MolScribe:
    """MolScribe: chemical structure image → E-SMILES.

    Lazy-loads model on construction; gracefully degrades if model/unavailable.
    """

    def __init__(self, config: MolScribeConfig | None = None) -> None:
        self.config = config or MolScribeConfig()
        self._engine: MolScribeEngine | None = None
        self._available: bool = False
        self._error: str = ""
        self._init()

    def _init(self) -> None:
        dev = self.config.device
        if dev == "auto" and not is_gpu_available():
            logger.warning("No GPU detected — MolScribe will run on CPU")
        try:
            self._engine = MolScribeEngine(self.config)
            self._available = True
            logger.info("MolScribe loaded successfully")
        except Exception as exc:
            self._error = str(exc)
            self._available = False
            logger.error("MolScribe load failed: %s", exc)

    @property
    def is_available(self) -> bool:
        return self._available and self._engine is not None and self._engine.is_loaded()

    @property
    def error(self) -> str:
        return self._error

    def predict(self, image: Image.Image | np.ndarray) -> MolScribeResult:
        if not self.is_available:
            return MolScribeResult("", 0.0, success=False, error=self._error or "model not available")
        return self._engine.predict(image)

    def predict_batch(self, images: list) -> list[MolScribeResult]:
        if not self.is_available:
            err = self._error or "model not available"
            return [MolScribeResult("", 0.0, success=False, error=err) for _ in images]
        return self._engine.predict_batch(images)

    def __call__(self, image: Image.Image | np.ndarray) -> MolScribeResult:
        return self.predict(image)


# ---- Singleton accessors (moved from model_server/models/molscribe.py) ----

from typing import Any

_molscribe_instance: Any = None


def get_molscribe() -> MolScribe:
    """获取全局 MolScribe 单例（首次调用时加载模型）."""
    global _molscribe_instance
    if _molscribe_instance is None:
        _molscribe_instance = MolScribe()
        if _molscribe_instance.is_available:
            logger.info("MolScribe model loaded (singleton)")
        else:
            logger.warning("MolScribe model not available: %s", _molscribe_instance.error)
    return _molscribe_instance


def reset_molscribe() -> None:
    """重置 MolScribe 单例."""
    global _molscribe_instance
    _molscribe_instance = None


__all__ = [
    "MolScribe",
    "MolScribeConfig",
    "MolScribeResult",
    "get_molscribe",
    "reset_molscribe",
]
