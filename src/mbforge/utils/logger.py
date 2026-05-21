"""MBForge 日志配置.

使用方式:
    from ..utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("消息")
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from .constants import APP_NAME, GLOBAL_DATA_DIR


# 日志格式
_CONSOLE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_FILE_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"
)

# 日期格式
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_logger_initialized = False


def setup_logging(
    level: int = logging.INFO,
    log_dir: Optional[Path] = None,
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
    global _logger_initialized
    if _logger_initialized:
        return

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 清除已有 handler，避免重复
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 控制台输出
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
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
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(
                logging.Formatter(_FILE_FORMAT, datefmt=_DATE_FORMAT)
            )
            root_logger.addHandler(file_handler)
        except Exception:
            # 文件日志初始化失败不影响运行
            pass

    _logger_initialized = True


def get_logger(name: str) -> logging.Logger:
    """获取命名日志器.

    如果全局日志尚未初始化，会自动执行默认初始化。
    """
    if not _logger_initialized:
        setup_logging()
    return logging.getLogger(name)
