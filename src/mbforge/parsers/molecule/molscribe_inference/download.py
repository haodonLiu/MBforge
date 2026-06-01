"""MolScribe 模型下载 — 仅下载推理所需的 checkpoint.

统一使用 ResourceManager 管理路径，仓库 ID 为 yujieq/MolScribe。
"""

import os
from pathlib import Path

MODEL_ID = "yujieq/MolScribe"
CHECKPOINT_NAME = "swin_base_char_aux_1m680k.pth"


def get_model_dir() -> Path:
    """获取 MolScribe 模型目录（优先 ResourceManager，其次环境变量，最后默认路径）."""
    # 1. 环境变量覆盖
    env_dir = os.environ.get("MBFORGE_MOLSCRIBE_DIR")
    if env_dir:
        return Path(env_dir)

    # 2. 通过 ResourceManager 查找已下载的模型
    try:
        from mbforge.core.resource_manager import ResourceManager
        path = ResourceManager.get_molscribe_path()
        if path is not None:
            # get_molscribe_path 返回 checkpoint 文件路径或目录
            return path.parent if path.is_file() else path
    except ImportError:
        pass

    # 3. 默认路径（统一使用 get_model_cache_dir）
    try:
        from mbforge.utils.constants import get_model_cache_dir
        return Path(get_model_cache_dir()) / "MolScribe"
    except ImportError:
        return Path.home() / ".cache" / "mbforge" / "models" / "MolScribe"


def is_model_available(model_dir: Path | None = None) -> bool:
    d = model_dir or get_model_dir()
    # 检查 checkpoint 文件
    if (d / CHECKPOINT_NAME).exists():
        return True
    # 检查 safetensors（transformers 格式）
    if any(d.glob("*.safetensors")):
        return True
    return False


def ensure_molscribe_model(model_dir: Path | None = None) -> str:
    """确保模型已下载，返回 checkpoint 路径."""
    d = model_dir or get_model_dir()
    if is_model_available(d):
        ckpt = d / CHECKPOINT_NAME
        if ckpt.exists():
            return str(ckpt)
        # 返回目录路径（transformers 格式）
        return str(d)

    # 通过 ResourceManager 下载
    try:
        from mbforge.core.resource_manager import ResourceManager
        result = ResourceManager.ensure("molscribe")
        if result.status.value == "ready" and result.local_path:
            return result.local_path
    except ImportError:
        pass

    # 回退：直接 ModelScope 下载
    print("正在从 ModelScope 下载 MolScribe ...")
    try:
        from modelscope import snapshot_download
        snapshot_download(MODEL_ID)
    except ImportError:
        raise RuntimeError("需要: pip install modelscope")
    except Exception as e:
        raise RuntimeError(f"下载失败: {e}")

    if not is_model_available(d):
        raise RuntimeError(f"下载完成但找不到 {CHECKPOINT_NAME}")
    return str(d / CHECKPOINT_NAME)
