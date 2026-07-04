"""MBForge 日志配置.

使用方式:
    from ..utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("消息")
"""

from __future__ import annotations

import functools
import inspect
import logging
import os
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from .constants import APP_NAME, GLOBAL_DATA_DIR

# 日志格式 —— 增加进程ID、线程名，方便多线程/多进程诊断
_CONSOLE_FORMAT = "%(asctime)s | %(levelname)-8s | %(process)d:%(threadName)s | %(name)s | %(message)s"
_FILE_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(process)d:%(threadName)s | %(name)s | "
    "%(funcName)s:%(lineno)d | %(message)s"
)

_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_logger_initialized = False
_log_level: int = logging.INFO


def setup_logging(
    level: int = logging.INFO,
    log_dir: Path | None = None,
    console: bool = True,
    file: bool = True,
) -> None:
    """配置全局日志.

    Args:
        level: 日志级别 (logging.DEBUG/INFO/WARNING/ERROR)
        log_dir: 日志文件目录，默认 ~/.local/share/MBForge/logs
        console: 是否输出到控制台
        file: 是否输出到文件
    """
    global _logger_initialized, _log_level
    if _logger_initialized:
        # 允许动态调整级别
        root = logging.getLogger()
        root.setLevel(level)
        for h in root.handlers:
            h.setLevel(level)
        _log_level = level
        return

    _log_level = level
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 清除已有 handler，避免重复
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 控制台输出
    if console:
        # Windows zh-CN locale 下 sys.stdout.encoding 可能是 gbk，无法编码 ✓/✗
        # 这类 Unicode 字符。优先用环境变量注入 UTF-8 (PYTHONIOENCODING=utf-8)，
        # 如果 stdout 实际不是 utf-8 就用 backslashreplace 包一层兜底，保证 ✓
        # 不会让 StreamHandler 在 emit 时崩。
        console_stream = sys.stdout
        stdout_encoding = getattr(console_stream, "encoding", None)
        if stdout_encoding and stdout_encoding.lower().replace("-", "") != "utf8":
            try:
                import io

                console_stream = io.TextIOWrapper(
                    console_stream.buffer,
                    encoding="utf-8",
                    errors="backslashreplace",
                    line_buffering=True,
                )
            except (AttributeError, OSError):
                # 已经是 wrapper 或没有 buffer 属性 —— 退回到原 stream
                pass
        console_handler = logging.StreamHandler(console_stream)
        console_handler.setLevel(level)
        console_handler.setFormatter(
            logging.Formatter(_CONSOLE_FORMAT, datefmt=_DATE_FORMAT)
        )
        root_logger.addHandler(console_handler)

    # 文件输出
    if file:
        log_dir = log_dir or (GLOBAL_DATA_DIR / "logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{APP_NAME.lower()}.log"

        try:
            from logging.handlers import RotatingFileHandler

            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=20 * 1024 * 1024,  # 20 MB
                backupCount=10,
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(
                logging.Formatter(_FILE_FORMAT, datefmt=_DATE_FORMAT)
            )
            root_logger.addHandler(file_handler)
        except Exception as e:
            # 文件日志初始化失败不影响运行，但要打一条控制台日志
            fallback = logging.StreamHandler(sys.stderr)
            fallback.setFormatter(
                logging.Formatter(_CONSOLE_FORMAT, datefmt=_DATE_FORMAT)
            )
            root_logger.addHandler(fallback)
            root_logger.error(f"文件日志初始化失败: {e}")

    _logger_initialized = True
    root_logger.info(
        f"日志系统初始化完成 | 级别={logging.getLevelName(level)} | 目录={log_dir}"
    )


def get_logger(name: str) -> logging.Logger:
    """获取命名日志器.

    如果全局日志尚未初始化，会自动执行默认初始化。
    """
    if not _logger_initialized:
        # 支持通过环境变量 MBFORGE_LOG_LEVEL 控制初始级别
        env_level = os.environ.get("MBFORGE_LOG_LEVEL", "INFO").upper()
        level = getattr(logging, env_level, logging.INFO)
        setup_logging(level=level)
    return logging.getLogger(name)


# ---------- 诊断工具 ----------

T = TypeVar("T")


def log_call(
    level: int = logging.DEBUG,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """装饰器：自动记录函数进入/退出及耗时.

    用法:
        @log_call()
        def my_func(x, y):
            ...
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        func_name = f"{func.__module__}.{func.__qualname__}"
        func_logger = get_logger(func.__module__)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 构建参数摘要（避免记录过大对象）
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            args_summary = []
            for k, v in bound.arguments.items():
                if k in ("self", "cls"):
                    continue
                rep = repr(v)
                if len(rep) > 80:
                    rep = rep[:77] + "..."
                args_summary.append(f"{k}={rep}")
            args_str = ", ".join(args_summary)

            func_logger.log(level, f"[CALL] → {func_name}({args_str})")
            import time

            t0 = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed = (time.perf_counter() - t0) * 1000
                func_logger.log(level, f"[OK]   ← {func_name} | {elapsed:.1f}ms")
                return result
            except Exception as e:
                elapsed = (time.perf_counter() - t0) * 1000
                func_logger.log(
                    logging.ERROR,
                    f"[ERR]  ← {func_name} | {elapsed:.1f}ms | {type(e).__name__}: {e}",
                )
                raise

        return wrapper

    return decorator


def log_exception(logger: logging.Logger, msg: str = "") -> None:
    """记录当前异常及完整堆栈.

    用法:
        try:
            ...
        except Exception:
            log_exception(logger, "PDF渲染失败")
    """
    exc_text = traceback.format_exc()
    prefix = f"{msg} | " if msg else ""
    logger.error(f"{prefix}异常详情:\n{exc_text}")
