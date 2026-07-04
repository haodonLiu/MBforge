r"""配置加载与管理 — 单一 JSON + 单一 Pydantic schema.

物理文件: `{GLOBAL_CONFIG_DIR}/settings.json`
  - Windows: `%APPDATA%\MBForge\settings.json`
  - Linux/macOS: `~/.config/MBForge/settings.json`

历史 `config.json` / `gui_state.json` 在首次启动时自动迁移到 `settings.json`，
然后删除旧文件。

唯一访问入口（任何模块必须仅通过这些入口访问配置）:
  - load_global_config() -> AppConfig    单读 + lru_cache
  - save_global_config(cfg)              单写 + cache_clear
  - update_settings(partial: dict)       局部更新 + 校验 + 持久化
  - reset_settings()                     回到默认 + 持久化
  - reset_config_cache()                 测试辅助:清空 lru_cache

直接读 `os.environ["MBFORGE_*"]` 仅允许 `MBFORGE_FORCE_CPU` 等纯运行时开关。
LLM/OCR/cache 等业务配置统一走 AppConfig。
"""

from __future__ import annotations

import contextlib
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .helpers import load_json, save_json
from .paths import GLOBAL_CONFIG_DIR


class RecentProject(BaseModel):
    """最近打开的项目 — Web + DPG 共享 schema,通过 /api/v1/settings 持久化."""

    model_config = ConfigDict(extra="ignore")

    root: str
    name: str


class LLMConfig(BaseModel):
    """LLM for OpenKB indexing + query (LiteLLM format)."""

    model_config = ConfigDict(extra="ignore")

    provider: str = "openai_compatible"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    pageindex_threshold: int = 20
    language: str = "en"


class AppConfig(BaseSettings):
    """全局应用配置 — 唯一 schema."""

    model_config = SettingsConfigDict(
        env_prefix="MBFORGE_",
        extra="ignore",
    )

    llm: LLMConfig = Field(default_factory=LLMConfig)
    model_cache_dir: str = ""
    theme: str = "dark"
    language: str = "zh-CN"
    auto_open_project: bool = True
    vlm: dict[str, Any] = Field(default_factory=dict)
    ocr: dict[str, Any] = Field(default_factory=dict)
    model_server: dict[str, Any] = Field(default_factory=dict)
    recent_projects: list[RecentProject] = Field(default_factory=list)
    pdf_parse: dict[str, Any] = Field(default_factory=dict)
    moldet: dict[str, Any] = Field(default_factory=dict)
    ingest: dict[str, Any] = Field(default_factory=dict)


# 历史文件名（用于一次性迁移）
_LEGACY_PATHS: tuple[Path, ...] = (
    GLOBAL_CONFIG_DIR / "config.json",
    GLOBAL_CONFIG_DIR / "gui_state.json",
)
_SETTINGS_PATH = GLOBAL_CONFIG_DIR / "settings.json"


def _migrate_legacy_configs() -> None:
    """一次性合并 config.json + gui_state.json 到 settings.json,然后删除旧文件.

    - config.json 内容整体作为 settings.json 的起点
    - gui_state.json 的 recent_projects: list[{root,name}] 并入(去重,新者在前)
    """
    if _SETTINGS_PATH.exists():
        return

    merged: dict[str, Any] = {}
    for legacy in _LEGACY_PATHS:
        if not legacy.exists():
            continue
        data = load_json(legacy)
        if data is None:
            continue
        if legacy.name == "gui_state.json":
            # 老格式: recent_projects: list[{root,name}]
            items = data.get("recent_projects", [])
            existing = merged.setdefault("recent_projects", [])
            seen = {p.get("root") for p in existing if isinstance(p, dict)}
            for item in items:
                if not isinstance(item, dict):
                    continue
                root = item.get("root")
                if not root or root in seen:
                    continue
                seen.add(root)
                existing.append({"root": root, "name": item.get("name", root)})
        else:
            # config.json: 浅合并顶层
            for k, v in data.items():
                merged.setdefault(k, v)
        with contextlib.suppress(OSError):
            legacy.unlink()

    if merged:
        try:
            cfg = AppConfig.model_validate(merged)
            save_json(_SETTINGS_PATH, cfg.model_dump())
        except Exception:
            # 迁移失败:留待下次启动重试
            pass


@lru_cache(maxsize=1)
def load_global_config() -> AppConfig:
    """读取 settings.json;缺失/损坏 → 默认值(env + BaseSettings 驱动)."""
    _migrate_legacy_configs()
    if _SETTINGS_PATH.exists():
        data = load_json(_SETTINGS_PATH)
        if data is not None:
            try:
                return AppConfig.model_validate(data)
            except Exception:  # noqa: BLE001 — corrupt file, fall through to defaults
                pass
    cfg = AppConfig()
    save_global_config(cfg)
    return cfg


def save_global_config(config: AppConfig) -> None:
    """持久化并清空 lru_cache."""
    load_global_config.cache_clear()
    save_json(_SETTINGS_PATH, config.model_dump())


def update_settings(partial: dict[str, Any]) -> AppConfig:
    """Deep-merge `partial` 到当前配置 → 校验 → 持久化.

    Returns 新 AppConfig.输入不合法时抛 pydantic.ValidationError.
    """
    current = load_global_config().model_dump()

    def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                _deep_merge(base[k], v)
            else:
                base[k] = v
        return base

    _deep_merge(current, partial)
    new_cfg = AppConfig.model_validate(current)
    save_global_config(new_cfg)
    return new_cfg


def reset_settings() -> AppConfig:
    """回到默认配置并持久化."""
    cfg = AppConfig()
    save_global_config(cfg)
    return cfg


def reset_config_cache() -> None:
    """测试辅助:清空 lru_cache."""
    load_global_config.cache_clear()
