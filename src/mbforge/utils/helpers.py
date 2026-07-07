"""通用辅助函数."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json as _json
import logging as _logging
import os as _os
import re
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from PIL import Image


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


def split_text_chunks(
    text: str, chunk_size: int = 512, overlap: int = 128
) -> list[str]:
    """按字符数分块，优先在段落/句子边界分割.

    注意：DocumentProcessor 已不再使用此函数（改用 section-level 分块）。
    保留作为通用文本切分工具供其他模块使用。
    """
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


def ensure_dir(path: Path) -> None:
    """确保目录存在."""
    path.mkdir(parents=True, exist_ok=True)


def save_json(path: Path, data: Any) -> None:
    """将数据保存为 JSON 文件（缩进 2 空格）."""
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(path: Path, default: Any = None) -> Any:
    """加载 JSON 文件，失败时返回默认值.

    Any `OSError` (missing file, permission denied) or `JSONDecodeError`
    (corrupt file) returns the supplied default rather than propagating —
    callers use this for "best-effort" config lookups where a missing or
    corrupt file should not crash startup.
    """
    try:
        with open(path, encoding="utf-8") as f:
            return _json.load(f)
    except Exception:  # noqa: BLE001 — see docstring; this is a "tolerate corrupt config" helper, not a parser.
        return default


def run_sync(sync_func: Callable[..., Any], *args: Any) -> Any:
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


def decode_base64_to_tempfile(image_base64: str, ext: str = "png") -> str:
    """将 base64 编码的图片解码到临时文件，返回文件路径."""
    data = base64.b64decode(image_base64)
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
        f.write(data)
        return f.name


def decode_base64_image(image_base64: str) -> Image.Image:
    """将 base64 编码的图片解码为 PIL Image 对象."""
    from io import BytesIO

    from PIL import Image

    data = base64.b64decode(image_base64)
    return Image.open(BytesIO(data))


# ---- Exceptions (moved from exceptions.py) ----


# Severity levels for hierarchical error categorization.
# Maps to standard log levels when recorded to the structured log/ring buffer.
Severity = Literal["debug", "info", "warning", "error", "fatal"]

_SEVERITY_BY_STATUS: dict[int, str] = {
    400: "warning",
    401: "warning",
    403: "warning",
    404: "info",
    409: "warning",
    422: "warning",
    500: "error",
    502: "error",
    503: "error",
    504: "error",
}


def http_status_to_severity(status: int) -> Severity:
    """Map an HTTP status code to a Severity, with 'error' as the fallback."""
    return _SEVERITY_BY_STATUS.get(status, "error")  # type: ignore[return-value]


class MBForgeError(Exception):
    """Base exception with HTTP status code, error code, and structured context.

    New (vs. the original two-arg form) fields:
        severity:  hierarchical log level — see the `Severity` literal.
                   Determines log record level AND frontend toast treatment.
        category:  module/layer tag (e.g. 'pipeline.runner', 'routers.library').
                   Defaults to the defining module of the exception subclass.
        context:   arbitrary JSON-serializable dict captured alongside the
                   record. Used by exception handlers and the diagnostics
                   ring buffer.
    """

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        detail: str | None = None,
        severity: Severity = "error",
        category: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.detail = detail
        self.severity: Severity = severity
        self.category: str = category or self.__class__.__module__
        self.context: dict[str, Any] = context or {}
        super().__init__(message)


class ProjectNotValidError(MBForgeError):
    status_code = 400
    error_code = "project_not_valid"


class ModelNotAvailableError(MBForgeError):
    status_code = 503
    error_code = "model_not_available"


class ConfigError(MBForgeError):
    status_code = 400
    error_code = "config_error"


class ValidationError(MBForgeError):
    status_code = 422
    error_code = "validation_error"


class FileAccessError(MBForgeError):
    status_code = 400
    error_code = "file_access_error"


class PathTraversalError(MBForgeError):
    status_code = 403
    error_code = "path_traversal"



class ResourceNotAvailableError(MBForgeError):
    status_code = 503
    error_code = "resource_not_available"


class ToolExecutionError(MBForgeError):
    status_code = 500
    error_code = "tool_execution_error"


# ---- GPU helpers (moved from gpu.py) ----

_gpu_logger = _logging.getLogger(__name__)
_gpu_cached: bool | None = None


def is_gpu_available() -> bool:
    """Check if NVIDIA GPU with CUDA is available."""
    global _gpu_cached
    if _gpu_cached is not None:
        return _gpu_cached
    if _os.environ.get("MBFORGE_FORCE_CPU", "").strip() == "1":
        _gpu_cached = False
        return False
    try:
        import torch  # noqa: F401

        available = torch.cuda.is_available()
    except ImportError:
        available = False
    _gpu_cached = available
    return available


def require_gpu() -> bool:
    """Return True if GPU is required (not forced to CPU)."""
    return is_gpu_available()


def gpu_warning(feature: str) -> None:
    """Log a one-time warning that feature is disabled due to no GPU."""
    _gpu_logger.warning(
        "No GPU available — %s requires CUDA. "
        "Set MBFORGE_FORCE_CPU=1 to suppress this warning, "
        "or install NVIDIA drivers and CUDA toolkit to enable.",
        feature,
    )


def check_environment() -> None:
    """检查环境资源状态（共享逻辑，供 app.py 和 server.py 调用）。"""
    try:
        from ..core.resource_manager import ResourceManager

        report = ResourceManager.check_all()
        _gpu_logger.info("Environment: %s", report.summary)
        for r in report.resources:
            icon = "✓" if r.status.value == "ready" else "✗"
            _gpu_logger.info("  %s %s: %s", icon, r.name, r.status.value)
    except Exception as e:
        _gpu_logger.warning("Environment check failed: %s", e)


def shutdown_backends() -> None:
    """卸载所有后端模型（共享逻辑）。"""
    from ..backends import moldet, molscribe

    for mod in [molscribe, moldet]:
        try:
            mod.unload()
        except Exception:
            pass


def resolve_root(body: dict | None = None) -> str:
    """从请求 body（或全局配置）解析 root 目录，兼容新旧字段名。

    优先级: library_root > libraryRoot > project_root > projectRoot > 全局配置
    """
    from .config import load_global_config

    b = body or {}
    root = (
        b.get("library_root", "")
        or b.get("libraryRoot", "")
        or b.get("project_root", "")
        or b.get("projectRoot", "")
    )
    if root:
        return validate_path(root)
    cfg = load_global_config()
    if cfg.library_root:
        return str(Path(cfg.library_root).resolve())
    return ""


def validate_path(root: str) -> str:
    """验证路径安全，返回规范化后的字符串。无 body 场景替代 validate_project_root."""
    if not root or not root.strip():
        raise ValidationError("root path is required")
    path = Path(root).resolve()
    if ".." in str(path):
        raise PathTraversalError(f"Path traversal detected: {root}")
    if not path.is_absolute():
        raise ValidationError(f"Path must be absolute: {root}")
    return str(path)
