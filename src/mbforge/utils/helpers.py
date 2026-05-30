"""通用辅助函数."""

from __future__ import annotations

import asyncio
import hashlib
import json as _json
import re
import uuid
from pathlib import Path
from typing import Any


def get_default_device() -> str:
    """自动检测可用加速设备，优先 GPU.

    顺序: cuda -> mps (Apple Silicon) -> cpu
    """
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


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


def _current_section(
    char_pos: int, headings: list[dict[str, Any]]
) -> str:
    """根据字符位置确定当前 chunk 属于哪个 section."""
    if not headings:
        return ""
    # 计算每个 heading 的字符位置
    lines = []
    current_line_start = 0
    for i, ch in enumerate(text):
        if ch == "\n":
            lines.append(current_line_start)
            current_line_start = i + 1
    # 找到当前位置之前的最后一个 heading
    current = ""
    for h in headings:
        line_num = h.get("line_num", 1)
        # 简化为按行号映射到字符位置
        line_start = 0
        line_count = 1
        for i, ch in enumerate(text):
            if ch == "\n":
                line_count += 1
            if line_count == line_num:
                line_start = i + 1
                break
        if line_start <= char_pos:
            current = h["title"]
        else:
            break
    return current


def split_text_chunks(
    text: str,
    chunk_size: int = 512,
    overlap: int = 128,
    headings: list[dict[str, Any]] | None = None,
) -> list[str]:
    """按字符数分块，优先在段落/句子边界分割.

    Args:
        headings: 文档 heading 层级列表。如提供，会在每个 chunk 头部注入
                  [Section: title] 上下文（参考 RAGFlow Contextual Chunking 思想）.
    """
    chunks = []
    start = 0
    text_len = len(text)

    # 预计算 heading 到字符位置的映射
    heading_positions: list[tuple[int, str]] = []
    if headings:
        line_to_pos = {1: 0}
        pos = 0
        line_num = 1
        for ch in text:
            if ch == "\n":
                line_num += 1
                line_to_pos[line_num] = pos + 1
            pos += 1
        for h in headings:
            ln = h.get("line_num", 1)
            heading_positions.append((line_to_pos.get(ln, 0), h["title"]))

    def _section_at(pos: int) -> str:
        """返回 pos 位置对应的 section 标题."""
        title = ""
        for hp, ht in heading_positions:
            if hp <= pos:
                title = ht
            else:
                break
        return title

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
        chunk_text = text[start:end].strip()
        if chunk_text:
            # 注入 section 上下文（参考 RAGFlow table_context_size 思想简化版）
            if heading_positions:
                sec = _section_at(start)
                if sec:
                    chunk_text = f"[Section: {sec}]\n{chunk_text}"
            chunks.append(chunk_text)
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
