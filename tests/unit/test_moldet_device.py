"""P1.3 — moldet device 必须走 cfg，不再回退到 MBFORGE_DEVICE env.

锁定决策 D2：``_resolve_device`` 优先级 = arg > cfg > "auto"，env 兜底已删除。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mbforge.utils import config as cfg_mod
from mbforge.utils.config import (
    load_global_config,
    reset_config_cache,
    update_settings,
)


@pytest.fixture
def tmp_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """与 tests/unit/test_config.py 同样的 fixture 模式."""
    settings = tmp_path / "settings.json"
    legacy_cfg = tmp_path / "config.json"
    legacy_gui = tmp_path / "gui_state.json"
    monkeypatch.setattr(cfg_mod, "_SETTINGS_PATH", settings)
    monkeypatch.setattr(cfg_mod, "_LEGACY_PATHS", (legacy_cfg, legacy_gui))
    reset_config_cache()
    yield tmp_path
    reset_config_cache()


class TestResolveDevice:
    def test_explicit_arg_wins(self, tmp_settings, monkeypatch: pytest.MonkeyPatch) -> None:
        """显式 arg 压倒 cfg / env."""
        from mbforge.backends import moldet

        update_settings({"moldet": {"device": "cuda:1"}})
        monkeypatch.setenv("MBFORGE_DEVICE", "cpu")
        assert moldet._resolve_device("cuda:0") == "cuda:0"

    def test_cfg_used_when_arg_empty(self, tmp_settings) -> None:
        """arg 为空时取 cfg.moldet.device."""
        from mbforge.backends import moldet

        update_settings({"moldet": {"device": "cuda:0"}})
        assert moldet._resolve_device(None) == "cuda:0"

    def test_model_server_device_takes_priority_over_moldet(self, tmp_settings) -> None:
        """与 moldet.py:755 singleton 路径一致: model_server.device 优先."""
        from mbforge.backends import moldet

        update_settings({
            "model_server": {"device": "cuda:0"},
            "moldet": {"device": "cuda:1"},
        })
        assert moldet._resolve_device(None) == "cuda:0"

    def test_fallback_to_auto(self, tmp_settings) -> None:
        """空 arg + 空 cfg → "auto"."""
        from mbforge.backends import moldet

        assert moldet._resolve_device(None) == "auto"

    def test_mbforge_device_env_no_longer_used(
        self, tmp_settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """锁定 D2: 即使 env 设了 MBFORGE_DEVICE=cpu,_resolve_device(None) 也不应回退到 env.

        这是 Phase 1 决策守护测试 —— 一旦有人重新引入 env 兜底,本测试会失败.
        """
        from mbforge.backends import moldet

        monkeypatch.setenv("MBFORGE_DEVICE", "cpu")
        monkeypatch.delenv("MBFORGE_FORCE_CPU", raising=False)
        # cfg 为空 (default moldet={}), arg=None
        cfg = load_global_config()
        assert cfg.moldet == {}
        assert moldet._resolve_device(None) == "auto"  # 不是 "cpu"


class TestResolveDeviceIntegration:
    """验证三处 __init__ 都调用 _resolve_device —— 通过源码契约而非实例化（避免重型依赖）."""

    def test_moldetv2_doc_detector_uses_helper(self, tmp_settings) -> None:
        import inspect

        from mbforge.backends import moldet

        src = inspect.getsource(moldet.MolDetv2DocDetector.__init__)
        assert "_resolve_device(device)" in src
        assert "MBFORGE_DEVICE" not in src

    def test_molscribe_recognizer_uses_helper(self, tmp_settings) -> None:
        import inspect

        from mbforge.backends import moldet

        src = inspect.getsource(moldet.MolScribeRecognizer.__init__)
        assert "_resolve_device(device)" in src
        assert "MBFORGE_DEVICE" not in src

    def test_molimage_pipeline_uses_helper(self, tmp_settings) -> None:
        import inspect

        from mbforge.backends import moldet

        src = inspect.getsource(moldet.MolImagePipeline.__init__)
        assert "_resolve_device(device)" in src
        assert "MBFORGE_DEVICE" not in src
