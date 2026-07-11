r"""配置加载与管理 — 单一 JSON + 单一 Pydantic schema.

物理文件: `{GLOBAL_APP_DIR}/settings.json`
  - Windows: `C:\Users\<user>\MBForge\settings.json`
  - Linux/macOS: `~/MBForge/settings.json`

历史文件（`%APPDATA%/%LOCALAPPDATA%/MBForge/settings.json` 以及旧版
`config.json` / `gui_state.json`）在首次启动时自动迁移到新位置。

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

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .helpers import load_json, save_json
from .paths import GLOBAL_APP_DIR


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
    reorganize_model: str | None = Field(
        default=None,
        description="Model for text reorganization. Falls back to ``model`` if unset.",
    )


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
    library_root: str | None = Field(
        default=None, description="Unified library data directory (Zotero-style)"
    )
    pdf_parse: dict[str, Any] = Field(default_factory=dict)
    # moldet: 分子检测管线设置。
    # 已知 key: {"device", "molscribe_dir", "detection_dpi", "detection_batch_size"}.
    # detection_dpi: 分子检测渲染分辨率 (默认 200).
    # detection_batch_size: YOLO batch 推理页数 (0=逐页, 仅在 GPU 有显存收益).
    moldet: dict[str, Any] = Field(default_factory=dict)
    ingest: dict[str, Any] = Field(default_factory=dict)
    # popo: MinerU-Popo OCR 后处理可选配置 (4B Qwen3-VL, 本地推理).
    # 已知 key: {"enabled"}.
    # enabled: 是否在 pipeline 中启用 (默认 false).
    popo: dict[str, Any] = Field(default_factory=dict)


# 历史文件名（用于一次性迁移）
_LEGACY_PATHS: tuple[Path, ...] = (
    GLOBAL_APP_DIR / "config.json",
    GLOBAL_APP_DIR / "gui_state.json",
)
_SETTINGS_PATH = GLOBAL_APP_DIR / "settings.json"


def _legacy_platformdirs_settings_paths() -> list[Path]:
    """Return legacy platformdirs settings.json locations for migration."""
    try:
        from platformdirs import user_config_dir, user_data_dir
    except ImportError:  # pragma: no cover
        return []
    return [
        Path(user_config_dir("MBForge", appauthor=False)) / "settings.json",
        Path(user_data_dir("MBForge", appauthor=False)) / "settings.json",
    ]


def _migrate_legacy_configs() -> None:
    """一次性迁移旧配置到新的统一目录.

    迁移来源按优先级:
    1. 旧 platformdirs 位置的 settings.json (%APPDATA%/%LOCALAPPDATA%/MBForge/)
    2. 同一目录下的 config.json / gui_state.json

    迁移后旧文件保留(不删除),避免数据丢失;用户可手动清理旧 %APPDATA% 目录。
    """
    if _SETTINGS_PATH.exists():
        return

    merged: dict[str, Any] = {}

    # 1. 尝试从旧 platformdirs 位置读取 settings.json
    for legacy_settings in _legacy_platformdirs_settings_paths():
        if not legacy_settings.exists():
            continue
        data = load_json(legacy_settings)
        if isinstance(data, dict):
            merged.update(data)
            break

    # 2. 合并旧 config.json / gui_state.json(如果存在)
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
                cfg = AppConfig.model_validate(data)
                # 未设置 library_root 时默认指向统一应用目录
                if cfg.library_root is None or cfg.library_root == "":
                    cfg.library_root = str(GLOBAL_APP_DIR)
                    save_global_config(cfg)
                return cfg
            except Exception:  # noqa: BLE001 — corrupt file, fall through to defaults
                pass
    cfg = AppConfig()
    cfg.library_root = str(GLOBAL_APP_DIR)
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
