"""Optional Rust acceleration module.

If mbforge_core is not installed (no Rust toolchain), falls back to pure Python.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    import mbforge_core as _rust_core

    HAS_CORE = True
except ImportError:
    HAS_CORE = False
    _rust_core = None

if TYPE_CHECKING:
    import numpy as np


def pairwise_tanimoto_matrix(fps: list) -> "np.ndarray":
    """Compute pairwise Tanimoto similarity matrix for molecular fingerprints.

    Uses Rust acceleration if available, otherwise falls back to pure Python.
    """
    if HAS_CORE and _rust_core is not None:
        import numpy as np

        arrs = [np.asarray(fp, dtype=np.uint8) for fp in fps]
        return _rust_core.pairwise_tanimoto_matrix(arrs)

    # Pure Python fallback
    import numpy as np

    n = len(fps)
    if n == 0:
        return np.zeros((0, 0), dtype=np.float64)

    matrix = np.ones((n, n), dtype=np.float64)

    for i in range(n):
        for j in range(i + 1, n):
            a = np.asarray(fps[i], dtype=np.bool_)
            b = np.asarray(fps[j], dtype=np.bool_)
            intersection = np.sum(a & b)
            union = np.sum(a | b)
            sim = intersection / union if union > 0 else 0.0
            matrix[i, j] = sim
            matrix[j, i] = sim

    return matrix
