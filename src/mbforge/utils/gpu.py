"""GPU detection and device management.

Determines whether NVIDIA GPU with CUDA is available.
Used to gate GPU-required features (MolDet, MolScribe) at initialization time.

Usage:
    from mbforge.utils.gpu import is_gpu_available, require_gpu

    if not is_gpu_available():
        logger.warning("No GPU detected — MolDet/MolScribe image pipeline disabled")
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_cached: bool | None = None


def is_gpu_available() -> bool:
    """Check if NVIDIA GPU with CUDA is available.

    Cached after first call to avoid repeated torch import overhead.
    Respects MBFORGE_FORCE_CPU=1 to override detection.
    """
    global _cached
    if _cached is not None:
        return _cached

    if os.environ.get("MBFORGE_FORCE_CPU", "").strip() == "1":
        _cached = False
        return False

    try:
        import torch  # noqa: F401
        available = torch.cuda.is_available()
    except ImportError:
        available = False

    _cached = available
    return available


def require_gpu() -> bool:
    """Return True if GPU is required (not forced to CPU).

    MBFORGE_FORCE_CPU=1 bypasses all GPU features.
    """
    return is_gpu_available()


def gpu_warning(feature: str) -> None:
    """Log a one-time warning that feature is disabled due to no GPU."""
    logger.warning(
        "No GPU available — %s requires CUDA. "
        "Set MBFORGE_FORCE_CPU=1 to suppress this warning, "
        "or install NVIDIA drivers and CUDA toolkit to enable.",
        feature,
    )
