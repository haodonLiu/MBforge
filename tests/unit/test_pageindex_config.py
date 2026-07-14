"""Regression tests for persisted PageIndex settings."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

from mbforge.openkb import indexer
from mbforge.utils.config import AppConfig, PageIndexConfig


def test_pageindex_client_ignores_legacy_environment_configuration(
    monkeypatch,
    tmp_path,
) -> None:
    """The PageIndex client must receive only persisted business settings.

    The wrapper must pass ``api_key`` and ``api_base`` explicitly to
    ``PageIndexClient`` and must not mutate the global ``os.environ``.
    """
    created: dict[str, object] = {}

    class FakePageIndexClient:
        def __init__(self, **kwargs) -> None:
            created.update(kwargs)

    config = AppConfig(
        pageindex=PageIndexConfig(
            api_key="settings-key",
            base_url="https://settings.example/v1",
            model="settings-model",
        )
    )
    monkeypatch.setenv("PAGEINDEX_API_KEY", "legacy-pageindex-key")
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-openai-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://legacy.example/v1")
    monkeypatch.setattr(indexer, "load_global_config", lambda: config)
    monkeypatch.setitem(
        sys.modules,
        "pageindex",
        SimpleNamespace(PageIndexClient=FakePageIndexClient),
    )

    indexer.PageIndexWrapper(str(tmp_path))._get_client()

    assert created == {
        "api_key": "settings-key",
        "api_base": "https://settings.example/v1",
        "model": "openai/settings-model",
        "storage_path": str(tmp_path),
    }
    # The global environment must remain untouched.
    assert os.environ["OPENAI_API_KEY"] == "legacy-openai-key"
    assert os.environ["OPENAI_API_BASE"] == "https://legacy.example/v1"
