"""配置层回归网 — 单文件 settings.json + 单一 Pydantic schema."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from mbforge.utils import config as cfg_mod
from mbforge.utils.config import (
    AppConfig,
    RecentProject,
    load_global_config,
    reset_config_cache,
    reset_settings,
    save_global_config,
    update_settings,
)


@pytest.fixture
def tmp_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """把 settings.json / 旧 config.json / gui_state.json 重定向到 tmp_path."""
    settings = tmp_path / "settings.json"
    config_json = tmp_path / "config.json"
    gui_state = tmp_path / "gui_state.json"

    monkeypatch.setattr(cfg_mod, "_SETTINGS_PATH", settings)
    monkeypatch.setattr(cfg_mod, "_LEGACY_PATHS", (config_json, gui_state))
    reset_config_cache()
    yield tmp_path
    reset_config_cache()


class TestLoad:
    def test_returns_defaults_when_no_file(self, tmp_settings: Path) -> None:
        cfg = load_global_config()
        assert cfg.theme == "dark"
        assert cfg.language == "zh-CN"
        assert cfg.recent_projects == []
        assert cfg.llm.provider == "openai_compatible"
        # 默认值被持久化,下次读仍然是默认
        assert (tmp_settings / "settings.json").exists()

    def test_falls_back_to_defaults_on_corrupt_json(self, tmp_settings: Path) -> None:
        (tmp_settings / "settings.json").write_text("{ not json", encoding="utf-8")
        cfg = load_global_config()
        assert cfg.theme == "dark"  # corrupt 不抛,回退默认
        # 回写后文件应被覆盖为合法 JSON
        assert cfg.model_validate_json(
            (tmp_settings / "settings.json").read_text(encoding="utf-8")
        ).theme == "dark"


class TestSaveAndCache:
    def test_save_then_load_returns_same_instance(self, tmp_settings: Path) -> None:
        cfg1 = load_global_config()
        cfg1.theme = "light"
        cfg1.recent_projects = [RecentProject(root="/a", name="A")]
        save_global_config(cfg1)

        cfg2 = load_global_config()
        assert cfg2.theme == "light"
        assert cfg2.recent_projects[0].root == "/a"
        assert cfg2.recent_projects[0].name == "A"

    def test_lru_cache_invalidates_on_save(self, tmp_settings: Path) -> None:
        cfg_a = load_global_config()
        cfg_b = load_global_config()
        assert cfg_a is cfg_b  # cache 命中

        cfg_a.theme = "light"
        save_global_config(cfg_a)

        cfg_c = load_global_config()
        assert cfg_c.theme == "light"


class TestUpdate:
    def test_deep_merge_preserves_untouched_fields(self, tmp_settings: Path) -> None:
        load_global_config()
        new_cfg = update_settings({"llm": {"model": "qwen-turbo", "temperature": 0.2}})
        assert new_cfg.llm.model == "qwen-turbo"
        assert new_cfg.llm.temperature == pytest.approx(0.2)
        # 未触碰的字段保留
        assert new_cfg.llm.provider == "openai_compatible"
        assert new_cfg.theme == "dark"

    def test_recent_projects_round_trip(self, tmp_settings: Path) -> None:
        load_global_config()
        new_cfg = update_settings(
            {"recent_projects": [{"root": "/proj/a", "name": "A"}, {"root": "/proj/b", "name": "B"}]}
        )
        assert len(new_cfg.recent_projects) == 2
        assert new_cfg.recent_projects[0].root == "/proj/a"

        # 再读应该一致
        cfg_again = load_global_config()
        assert [p.root for p in cfg_again.recent_projects] == ["/proj/a", "/proj/b"]

    def test_validation_error_propagates(self, tmp_settings: Path) -> None:
        load_global_config()
        # temperature 类型不对
        with pytest.raises(ValidationError):
            update_settings({"llm": {"temperature": "not-a-number"}})


class TestReset:
    def test_reset_returns_to_defaults(self, tmp_settings: Path) -> None:
        load_global_config()
        update_settings({"theme": "light", "llm": {"model": "x"}})
        cfg = reset_settings()
        assert cfg.theme == "dark"
        assert cfg.llm.model == AppConfig().llm.model


class TestMigration:
    def test_migrates_legacy_config_json(self, tmp_settings: Path) -> None:
        (tmp_settings / "config.json").write_text(
            '{"theme": "light", "language": "en", "llm": {"model": "legacy"}}',
            encoding="utf-8",
        )
        cfg = load_global_config()
        assert cfg.theme == "light"
        assert cfg.language == "en"
        assert cfg.llm.model == "legacy"
        # 旧文件已删
        assert not (tmp_settings / "config.json").exists()
        assert (tmp_settings / "settings.json").exists()

    def test_migrates_gui_state_recent_projects(self, tmp_settings: Path) -> None:
        (tmp_settings / "gui_state.json").write_text(
            '{"recent_projects": [{"root": "/from-gui", "name": "GUIProj"}]}',
            encoding="utf-8",
        )
        cfg = load_global_config()
        assert len(cfg.recent_projects) == 1
        assert cfg.recent_projects[0].root == "/from-gui"
        assert cfg.recent_projects[0].name == "GUIProj"
        assert not (tmp_settings / "gui_state.json").exists()

    def test_settings_json_takes_precedence_over_legacy(self, tmp_settings: Path) -> None:
        # settings.json 已存在 → 不迁移
        (tmp_settings / "settings.json").write_text(
            '{"theme": "light"}',
            encoding="utf-8",
        )
        (tmp_settings / "config.json").write_text('{"theme": "dark"}', encoding="utf-8")
        cfg = load_global_config()
        assert cfg.theme == "light"
        # 旧文件保留(因为没动)
        assert (tmp_settings / "config.json").exists()
