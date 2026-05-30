"""MolScribe 模型下载 — 仅下载推理所需的 checkpoint."""

import os
from pathlib import Path

MODEL_ID = "polyai/MolScribe"
CHECKPOINT_NAME = "swin_base_char_aux_1m680k.pth"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "modelscope" / "hub" / "models" / "polyai" / "MolScribe"


def get_model_dir() -> Path:
    env_dir = os.environ.get("MBFORGE_MOLSCRIBE_DIR")
    return Path(env_dir) if env_dir else DEFAULT_CACHE_DIR


def is_model_available(model_dir: Path | None = None) -> bool:
    d = model_dir or get_model_dir()
    return (d / CHECKPOINT_NAME).exists()


def ensure_molscribe_model(model_dir: Path | None = None) -> str:
    """确保模型已下载，返回 checkpoint 路径."""
    d = model_dir or get_model_dir()
    if is_model_available(d):
        return str(d / CHECKPOINT_NAME)

    print(f"正在从 ModelScope 下载 MolScribe ...")
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
