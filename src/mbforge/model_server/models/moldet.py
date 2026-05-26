"""MolDet 模型管理（服务进程内）."""

from __future__ import annotations

from typing import Any

from mbforge.parsers.molecule.mol_image_pipeline import MolImagePipeline
from mbforge.utils.config import load_global_config

_moldet_instance: Any = None


def get_moldet() -> MolImagePipeline | None:
    global _moldet_instance
    if _moldet_instance is None:
        device = load_global_config().embed.device
        _moldet_instance = MolImagePipeline(device=device)
    return _moldet_instance


def reset_moldet() -> None:
    global _moldet_instance
    _moldet_instance = None
