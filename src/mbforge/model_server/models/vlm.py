"""VLM 模型管理（服务进程内）."""

from __future__ import annotations

from .singleton import ModelSingleton
from mbforge.models.base import BaseVLM
from mbforge.models.vlm import create_vlm_from_config

_mgr = ModelSingleton(BaseVLM, lambda cfg: cfg.vlm, create_vlm_from_config)
get_vlm = _mgr.get
reset_vlm = _mgr.reset
