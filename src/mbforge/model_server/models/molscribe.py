"""MolScribe 模型管理（服务进程内单例）."""

from __future__ import annotations

from typing import Any

from mbforge.parsers.molecule.molscribe import MolScribe
from mbforge.utils.logger import get_logger

logger = get_logger(__name__)

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
    """重置单例（用于测试或模型重载）."""
    global _molscribe_instance
    _molscribe_instance = None
