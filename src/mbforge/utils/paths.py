"""应用元信息 + 路径 helper — 单一真相.

取代旧的 configs/constants.yaml → utils/constants.py 自动生成链.
仅保留真正静态、跨模块共享的常量.运行时配置走 settings.json.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from platformdirs import user_config_dir, user_data_dir
except ImportError:  # pragma: no cover — fallback for env without platformdirs
    _home = Path.home()

    def user_config_dir(name: str, **_kw: object) -> str:
        return str(_home / ".config" / name)

    def user_data_dir(name: str, **_kw: object) -> str:
        return str(_home / ".local" / "share" / name)


# 应用元信息 — 编译期固定,不改
APP_NAME = "MBForge"
APP_VERSION = "0.3.0"

# 跨平台配置 / 数据目录 — 仅在 settings.json 缺失时作 fallback 解析
GLOBAL_CONFIG_DIR = Path(user_config_dir(APP_NAME, appauthor=False))
GLOBAL_DATA_DIR = Path(user_data_dir(APP_NAME, appauthor=False))

# 后端 sidecar 端口 — __main__ 启动参数 fallback
DEFAULT_SIDECAR_PORT = 18792

# 模型缓存默认路径 — get_model_cache_dir() 在 settings.json 未配置时使用
DEFAULT_MODEL_CACHE_DIR = "mbforge/models"

# HF 镜像 endpoint — ensure_hf_mirror() 在 HF_ENDPOINT 未设置时使用
DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"


def get_model_cache_dir() -> str:
    """模型缓存目录(优先 settings.json,其次默认路径).

    Returns 展开 ~ 后的绝对路径字符串.
    """
    try:
        from .config import load_global_config

        cfg = load_global_config()
        if cfg.model_cache_dir:
            raw = cfg.model_cache_dir
            if raw.startswith("~/") or raw.startswith("~\\"):
                return str(Path.home() / raw[2:])
            if raw == "~":
                return str(Path.home())
            return raw
    except Exception:
        pass
    return str(Path.home() / DEFAULT_MODEL_CACHE_DIR)


def ensure_hf_mirror() -> None:
    """设置 HuggingFace 镜像环境变量(若未设置)."""
    if not os.environ.get("HF_ENDPOINT"):
        os.environ["HF_ENDPOINT"] = DEFAULT_HF_ENDPOINT
