"""通用辅助函数."""

from __future__ import annotations

import asyncio
import hashlib
import json as _json
import re
import uuid
from pathlib import Path
from typing import Any


def generate_uuid() -> str:
    """生成唯一标识符."""
    return str(uuid.uuid4())


def sha256_file(path: Path) -> str:
    """计算文件 SHA256."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    """计算文本 SHA256."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_filename(name: str) -> str:
    """将字符串转换为安全文件名."""
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def truncate_text(text: str, max_len: int = 200) -> str:
    """截断文本."""
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "..."


def split_text_chunks(
    text: str, chunk_size: int = 512, overlap: int = 128
) -> list[str]:
    """按字符数分块，优先在段落/句子边界分割."""
    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(start + chunk_size, text_len)
        if end < text_len:
            # 尝试在换行处分割
            nl = text.rfind("\n", start, end)
            if nl > start + chunk_size // 2:
                end = nl + 1
            else:
                # 尝试在句号处分割
                period = text.rfind("。", start, end)
                if period > start + chunk_size // 2:
                    end = period + 1
                else:
                    space = text.rfind(" ", start, end)
                    if space > start + chunk_size // 2:
                        end = space + 1
        chunks.append(text[start:end].strip())
        start = end - overlap
        if start < 0:
            start = 0
        if start >= end or start >= text_len:
            break
    return [c for c in chunks if c]


def format_molecule_info(
    smiles: str, name: str = "", activity: float | None = None
) -> str:
    """格式化分子信息为文本."""
    lines = [f"**SMILES**: `{smiles}`"]
    if name:
        lines.append(f"**Name**: {name}")
    if activity is not None:
        lines.append(f"**Activity**: {activity} nM")
    return "\n".join(lines)


def ensure_dir(path: Path) -> None:
    """确保目录存在."""
    path.mkdir(parents=True, exist_ok=True)


def save_json(path: Path, data: Any) -> None:
    """将数据保存为 JSON 文件（缩进 2 空格）."""
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(path: Path, default: Any = None) -> Any:
    """加载 JSON 文件，失败时返回默认值."""
    try:
        with open(path, encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return default


def run_sync(sync_func, *args) -> Any:
    """在当前事件循环的线程池中同步执行函数（异步兼容）."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(sync_func, *args)
            return future.result()
    return sync_func(*args)
