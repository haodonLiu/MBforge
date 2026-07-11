"""MolScribe 模型路径解析 — 仅读盘，不下载。

模型路径由 `mbforge.utils.config` + `ResourceManager` 解析到
`~/MBForge/models/MolScribe/` 后,本模块仅做 checkpoint 文件定位和
可用性探测。
"""

import os
from pathlib import Path

from mbforge.utils.config import load_global_config
from mbforge.utils.logger import get_logger

logger = get_logger(__name__)

MODEL_ID = "polyai/MolScribe"
CHECKPOINT_NAME = "swin_base_char_aux_1m680k.pth"


def get_model_dir() -> Path:
    """获取 MolScribe 模型目录.

    优先级:
      1. ``cfg.moldet["molscribe_dir"]`` (Settings UI)
      2. 环境变量 ``MBFORGE_MOLSCRIBE_DIR`` (legacy / 显式覆盖)
      3. ``ResourceManager.get_molscribe_path()`` (读 Rust resolved_paths.json)
      4. 缓存目录 ``<model_cache_dir>/MolScribe``
      5. 兜底 ``~/MBForge/models/MolScribe``
    """
    cfg = load_global_config()
    cfg_dir = cfg.moldet.get("molscribe_dir")
    if cfg_dir:
        return Path(cfg_dir)

    env_dir = os.environ.get("MBFORGE_MOLSCRIBE_DIR")
    if env_dir:
        return Path(env_dir)

    try:
        from mbforge.core.resource_manager import ResourceManager
        path = ResourceManager.get_molscribe_path()
        if path is not None:
            return path.parent if path.is_file() else path
    except ImportError:
        pass

    # 兜底：直接构造期望路径
    try:
        from mbforge.utils.paths import get_model_cache_dir
        return Path(get_model_cache_dir()) / "MolScribe"
    except ImportError:
        return Path.home() / "MBForge" / "models" / "MolScribe"


def is_model_available(model_dir: Path | None = None) -> bool:
    """检查 checkpoint 或 safetensors 是否在 `model_dir` 下."""
    d = model_dir or get_model_dir()
    return (d / CHECKPOINT_NAME).exists() or any(d.glob("*.safetensors"))
