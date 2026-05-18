"""配置管理模块.

从项目根目录的 .env 文件加载 UniParser 配置。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


@dataclass
class ParserConfig:
    """UniParser 配置."""

    host: str
    api_key: str

    def __post_init__(self) -> None:
        if not self.host:
            raise ValueError("host cannot be empty")
        if not self.api_key:
            raise ValueError("api_key cannot be empty")


def find_env_file() -> Optional[Path]:
    """查找项目根目录的 .env 文件."""
    current = Path.cwd()
    env_cwd = current / ".env"
    if env_cwd.exists():
        return env_cwd
    for parent in current.parents:
        env_file = parent / ".env"
        if env_file.exists():
            return env_file
    return None


def load_config() -> ParserConfig:
    """从 .env 加载配置."""
    env_file = find_env_file()
    if env_file and load_dotenv:
        load_dotenv(env_file)

    host = os.environ.get("UNIPARSER_HOST", "")
    api_key = os.environ.get("UNIPARSER_API_KEY", "")

    if not host:
        raise ValueError(
            "UNIPARSER_HOST is not set. "
            "Please set it in .env or environment variables."
        )
    if not api_key:
        raise ValueError(
            "UNIPARSER_API_KEY is not set. "
            "Please set it in .env or environment variables."
        )

    return ParserConfig(host=host, api_key=api_key)


def validate_config(config: ParserConfig) -> bool:
    """验证配置完整性."""
    if not config.host:
        return False
    if not config.host.startswith("http://") and not config.host.startswith("https://"):
        return False
    if not config.api_key:
        return False
    return True
