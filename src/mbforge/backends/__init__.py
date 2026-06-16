"""Fixed model backends — shared utilities."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from platformdirs import user_config_dir

logger = logging.getLogger("mbforge.backends")

_RESOLVED_PATHS_CACHE: dict[str, str] | None = None
_RESOLVED_PATHS_MTIME: float = 0.0

# Rust 端 ProjectDirs::from("", "", "MBForge") 的配置目录；用 platformdirs 镜像
# 跨平台路径（appauthor=False + roaming=True 才能匹配 Rust 的空 author/qualifier）：
#   Windows: %APPDATA%\MBForge\config
#   Linux:   ~/.config/MBForge
#   macOS:   ~/Library/Application Support/MBForge
_CONFIG_DIR = Path(user_config_dir(appname="MBForge", appauthor=False, roaming=True)) / "config"


def _read_resolved_paths() -> dict[str, str] | None:
    """读取 Rust 写入的 resolved_paths.json（按 mtime 失效的轻量缓存）."""
    global _RESOLVED_PATHS_CACHE, _RESOLVED_PATHS_MTIME
    path = _CONFIG_DIR / "resolved_paths.json"
    if not path.exists():
        return None
    try:
        mtime = path.stat().st_mtime
        if _RESOLVED_PATHS_CACHE is not None and mtime == _RESOLVED_PATHS_MTIME:
            return _RESOLVED_PATHS_CACHE
        with open(path) as f:
            data = json.load(f)
        _RESOLVED_PATHS_CACHE = data
        _RESOLVED_PATHS_MTIME = mtime
        logger.info(f"Loaded resolved paths from {path}: {list(data.keys())}")
        return data
    except Exception as e:
        logger.warning(f"Failed to read resolved_paths.json: {e}")
        return None


_MODEL_NAME_TO_RESOURCE_ID = {
    "Qwen/Qwen3-Embedding": "embedding",
    "Qwen/Qwen3-Reranker": "reranker",
    "UniParser/MolDetv2": "moldet",
    "MolDetv2": "moldet",
    "moldetv2": "moldet",
    "MolScribe": "molscribe",
    "moldetect-coref": "moldet_coref",
    "MolDetectCkpt": "moldet_coref",
}


def resolve_model_path(model_name: str, cache_name: str | None = None) -> str:
    """解析模型路径 — 统一走 ResourceManager.

    Rust resource_manager.rs 是路径解析的唯一真相源。
    """
    p = Path(model_name)
    if p.is_absolute() or (p.exists() and p.is_dir()):
        return str(model_name)

    # 尝试 ResourceManager
    try:
        from mbforge.core.resource_manager import ResourceManager
        resolved = _read_resolved_paths()
        rid = cache_name or model_name
        for prefix, mapped in _MODEL_NAME_TO_RESOURCE_ID.items():
            if prefix.lower() in rid.lower():
                path = ResourceManager.resolve_model_for_backend(mapped)
                if path is not None:
                    logger.info(f"Resolved {rid} → {path} (via ResourceManager)")
                    return str(path)
                # 回退到 Rust resolved_paths
                if resolved and mapped in resolved:
                    rpath = resolved[mapped]
                    if Path(rpath).exists():
                        logger.info(f"Resolved {rid} → {rpath} (via Rust resolved_paths)")
                        return rpath
    except ImportError:
        pass

    logger.info(f"No cached path for {model_name}")
    return model_name
