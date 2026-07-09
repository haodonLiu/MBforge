"""Thin compatibility shim — historical MolDetv2 + MolScribe pipeline.

The legacy detection stack (``MolDetv2DocDetector`` / ``MolDetv2GeneralDetector`` /
``MolImagePipeline`` / ``get_moldet()``) was replaced by the joint
``MolDetv2-FT`` detector on 2026-07-08 — see ``backends/moldet_v2_ft.py``.

This module is kept ONLY to provide:

* ``default_model_dir()`` — still imported by ``legacy_models.py`` and a few
  helpers; new code should import from ``moldet_v2_ft``.
* ``__getattr__`` shim — older imports of ``MolDetv2DocDetector`` /
  ``MolDetv2GeneralDetector`` / ``MolImagePipeline`` / ``get_moldet`` /
  ``reset_moldet`` / ``health`` raise a clear ``AttributeError`` pointing at
  the FT replacement. Callers should be migrated, not papered over.

The internal ``_BACKENDS`` registry and prewarm hooks in ``server.py`` no
longer reference this module.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["default_model_dir"]


def default_model_dir() -> Path:
    """返回模型缓存目录(使用统一常量).

    新代码应直接从 ``mbforge.backends.moldet_v2_ft`` 导入同名函数;
    此处保留仅为 legacy_models.py 与其他历史调用方。
    """
    from mbforge.utils.paths import get_model_cache_dir

    cache_dir = Path(get_model_cache_dir())
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


# Names removed in the 2026-07-08 FT migration. They are listed here so an
# accidental import (``from mbforge.backends import moldet; moldet.MolDetv2DocDetector()``)
# fails with a helpful pointer instead of an opaque AttributeError.
_REMOVED_NAMES: dict[str, str] = {
    "MolDetv2DocDetector": (
        "使用 mbforge.backends.moldet_v2_ft.MolDetv2FTDetector "
        "(联合检测,一次推理同时输出分子 + coref 标识符 bbox)"
    ),
    "MolDetv2GeneralDetector": (
        "已被 MolDetv2FTDetector 取代 — FT 模型一次推理同时完成整页 + 复检"
    ),
    "MolImagePipeline": (
        "已被废弃。新主链路 = MolDetv2FTDetector + MolScribe 端点; "
        "见 routers/moldet_api.py:/extract-pdf-page"
    ),
    "get_moldet": (
        "已删除。改用 mbforge.backends.moldet_v2_ft.get_moldet_ft()"
    ),
    "reset_moldet": "已删除(单例管理随 FT detector 一起迁移到 moldet_v2_ft)",
    "unload": "已删除(模型卸载随 molscribe 模块统一处理)",
    "health": "已删除(改用 routers/health.py 的资源状态检查)",
    "MolScribeRecognizer": "保留在 molscribe 后端,见 mbforge.backends.molscribe",
}


def __getattr__(name: str):  # PEP 562
    """Lazy fallback for removed symbols — clear error pointing at replacement."""
    if name in _REMOVED_NAMES:
        raise AttributeError(
            f"mbforge.backends.moldet.{name} 已被删除 (2026-07-08 FT 迁移). "
            f"{_REMOVED_NAMES[name]}"
        )
    raise AttributeError(f"module 'mbforge.backends.moldet' has no attribute {name!r}")
