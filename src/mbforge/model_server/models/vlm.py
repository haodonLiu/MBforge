"""VLM 模型管理（服务进程内）."""

from __future__ import annotations

from mbforge.models.base import BaseVLM
from mbforge.models.vlm import create_vlm_from_config

_vlm_instance: BaseVLM | None = None


def get_vlm() -> BaseVLM:
    global _vlm_instance
    if _vlm_instance is None:
        from mbforge.utils.config import load_global_config
        cfg = load_global_config().vlm
        _vlm_instance = create_vlm_from_config(cfg)
    return _vlm_instance


def reset_vlm() -> None:
    global _vlm_instance
    _vlm_instance = None
