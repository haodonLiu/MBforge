"""P1.2 — LLM factory 必须读 cfg.llm，不直接读 MBFORGE_LLM_* env.

锁定决策 D1：Settings UI 优先；env 通过 Pydantic env_prefix 间接生效。
"""

from __future__ import annotations

from pathlib import Path

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


class TestCreateLlmFromSettings:
    def test_reads_provider_from_cfg(
        self, tmp_settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """仅 cfg 有值时,create_llm_from_settings 用 cfg 构造 LLM."""
        # 显式清空所有相关 env,确保不污染
        for key in (
            "MBFORGE_LLM_PROVIDER",
            "MBFORGE_LLM_MODEL",
            "MBFORGE_LLM_API_KEY",
            "MBFORGE_LLM_BASE_URL",
        ):
            monkeypatch.delenv(key, raising=False)

        update_settings({
            "llm": {
                "provider": "openai_compatible",
                "model": "gpt-4o",
                "api_key": "sk-test",
                "base_url": "https://api.test/v1",
            }
        })

        from mbforge.agent.llm_factory import create_llm_from_settings

        llm = create_llm_from_settings()
        assert llm.model_name == "gpt-4o"
        assert llm.openai_api_key.get_secret_value() == "sk-test"
        assert "api.test" in str(llm.openai_api_base)

    def test_env_var_does_not_override_cfg(
        self, tmp_settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """核心断言: env 设了 ≠ UI 失守.

        Pydantic env_prefix 在 settings.json 已落盘后,后续 load 从 JSON 读;
        已经写入的 cfg.llm 不会被 env 覆盖.
        """
        # 1. 先写 settings.json(cfg 路径)
        update_settings({
            "llm": {
                "provider": "openai_compatible",
                "api_key": "sk-ui",
                "model": "gpt-ui",
                "base_url": "https://api.ui/v1",
            }
        })
        # 2. env 设一组不同的值 —— 应该不影响 cfg.llm
        monkeypatch.setenv("MBFORGE_LLM_API_KEY", "sk-env")
        monkeypatch.setenv("MBFORGE_LLM_MODEL", "gpt-env")

        from mbforge.agent.llm_factory import create_llm_from_settings

        llm = create_llm_from_settings()
        assert llm.model_name == "gpt-ui"  # UI wins
        assert llm.openai_api_key.get_secret_value() == "sk-ui"  # UI wins

    def test_no_cfg_no_env_raises(
        self, tmp_settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """退化路径: cfg.llm.api_key="" + env 也空 → ValueError."""
        for key in (
            "MBFORGE_LLM_PROVIDER",
            "MBFORGE_LLM_MODEL",
            "MBFORGE_LLM_API_KEY",
            "MBFORGE_LLM_BASE_URL",
        ):
            monkeypatch.delenv(key, raising=False)
        # cfg 默认 llm.api_key = ""

        from mbforge.agent.llm_factory import create_llm

        with pytest.raises(ValueError, match="api_key required"):
            create_llm(provider="openai_compatible")

    def test_env_var_fallback_when_cfg_empty(
        self, tmp_settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cfg 字段为空 + env 有值 → env 兜底（向后兼容 .env 用户）.

        Settings UI 不存在 / 未设过的情况下,.env 的 MBFORGE_LLM_API_KEY 仍生效.
        """
        for key in (
            "MBFORGE_LLM_PROVIDER",
            "MBFORGE_LLM_API_KEY",
            "MBFORGE_LLM_BASE_URL",
        ):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("MBFORGE_LLM_API_KEY", "sk-env-fallback")
        # cfg.llm.api_key 是空字符串(default),所以 env 兜底会触发

        from mbforge.agent.llm_factory import create_llm

        llm = create_llm(provider="openai_compatible")
        assert llm.openai_api_key.get_secret_value() == "sk-env-fallback"

    def test_env_is_secondary_to_cfg(
        self, tmp_settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """锁定 D1: cfg 和 env 都有值时,cfg 必胜.

        即使 env 设了不同的 model + api_key,UI 写入的 cfg.llm 仍然压倒.
        """
        update_settings({
            "llm": {
                "provider": "openai_compatible",
                "api_key": "sk-ui",
                "model": "gpt-ui",
            }
        })
        monkeypatch.setenv("MBFORGE_LLM_API_KEY", "sk-env")
        monkeypatch.setenv("MBFORGE_LLM_MODEL", "gpt-env")

        from mbforge.agent.llm_factory import create_llm

        llm = create_llm(provider="openai_compatible")
        assert llm.openai_api_key.get_secret_value() == "sk-ui"  # UI wins
        assert llm.model_name == "gpt-ui"  # UI wins

    def test_resolution_priority_arg_over_cfg_over_env(
        self, tmp_settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """完整优先级: explicit arg > cfg > env > default.

        三个值都给,只看 explicit arg 胜出.
        """
        update_settings({"llm": {"api_key": "sk-cfg"}})
        monkeypatch.setenv("MBFORGE_LLM_API_KEY", "sk-env")

        from mbforge.agent.llm_factory import create_llm

        llm = create_llm(provider="openai_compatible", api_key="sk-explicit")
        assert llm.openai_api_key.get_secret_value() == "sk-explicit"
