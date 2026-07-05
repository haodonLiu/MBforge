"""P1.4 — MolScribe 模型目录必须走 cfg.moldet.molscribe_dir,env 仅作第二级兜底."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mbforge.utils import config as cfg_mod
from mbforge.utils.config import (
    reset_config_cache,
    update_settings,
)


@pytest.fixture
def tmp_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """与 test_config.py 一致."""
    settings = tmp_path / "settings.json"
    legacy_cfg = tmp_path / "config.json"
    legacy_gui = tmp_path / "gui_state.json"
    monkeypatch.setattr(cfg_mod, "_SETTINGS_PATH", settings)
    monkeypatch.setattr(cfg_mod, "_LEGACY_PATHS", (legacy_cfg, legacy_gui))
    reset_config_cache()
    yield tmp_path
    reset_config_cache()


class TestGetModelDirCfgFirst:
    def test_cfg_wins_over_env(self, tmp_settings, monkeypatch: pytest.MonkeyPatch) -> None:
        """核心断言: cfg.moldet.molscribe_dir 压倒 MBFORGE_MOLSCRIBE_DIR."""
        from mbforge.parsers.molecule.molscribe_inference import download

        update_settings({"moldet": {"molscribe_dir": "/cfg/path"}})
        monkeypatch.setenv("MBFORGE_MOLSCRIBE_DIR", "/env/path")
        assert download.get_model_dir() == Path("/cfg/path")

    def test_env_used_when_cfg_absent(
        self, tmp_settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cfg 无值时回退到 env.

        env 检查在第 2 步就 return,根本到不了 ResourceManager 分支 —— 不需要 mock.
        """
        from mbforge.parsers.molecule.molscribe_inference import download

        # 默认 cfg.moldet = {},所以 molscribe_dir 是 None
        monkeypatch.setenv("MBFORGE_MOLSCRIBE_DIR", "/env/path")
        assert download.get_model_dir() == Path("/env/path")

    def test_resource_manager_used_when_cfg_and_env_empty(
        self, tmp_settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cfg + env 都空 → ResourceManager.get_molscribe_path()."""
        from mbforge.parsers.molecule.molscribe_inference import download

        monkeypatch.delenv("MBFORGE_MOLSCRIBE_DIR", raising=False)
        # Mock mbforge.core.resource_manager.ResourceManager.get_molscribe_path
        with patch(
            "mbforge.core.resource_manager.ResourceManager.get_molscribe_path",
            return_value=Path("/rust/path"),
        ):
            assert download.get_model_dir() == Path("/rust/path")

    def test_fallback_to_cache_dir(self, tmp_settings, monkeypatch: pytest.MonkeyPatch) -> None:
        """cfg + env + ResourceManager 全失败 → 缓存目录兜底."""
        from mbforge.parsers.molecule.molscribe_inference import download

        monkeypatch.delenv("MBFORGE_MOLSCRIBE_DIR", raising=False)
        # 把 ResourceManager 的 get_molscribe_path 模拟成 "not found"
        with patch(
            "mbforge.core.resource_manager.ResourceManager.get_molscribe_path",
            return_value=None,
        ):
            # 没传 molscribe_dir 时,fallback 应是 <cache>/MolScribe
            result = download.get_model_dir()
            assert result.name == "MolScribe"
