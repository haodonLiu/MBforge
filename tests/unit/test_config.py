"""Tests for mbforge.utils.config schema and helpers."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from mbforge.routers.settings import _redact_secrets
from mbforge.utils.config import (
    AppConfig,
    IngestConfig,
    LLMConfig,
    MoldetConfig,
    OCRConfig,
    PdfParseConfig,
    PopoConfig,
    VLMConfig,
    reset_config_cache,
    update_settings,
)


@pytest.fixture(autouse=True)
def _clear_config_cache() -> None:
    """Clear the config lru_cache before each test."""
    reset_config_cache()
    yield
    reset_config_cache()


class TestDefaultValues:
    """Default values must match the historical hard-coded fallbacks."""

    def test_llm_defaults(self) -> None:
        cfg = LLMConfig()
        assert cfg.provider == "openai_compatible"
        assert cfg.model == "gpt-4o-mini"
        assert cfg.temperature == pytest.approx(0.7)
        assert cfg.max_tokens == 4096
        assert cfg.top_p == pytest.approx(1.0)
        assert cfg.request_timeout == 60
        assert cfg.reorganize_model is None
        assert cfg.effective_model == "gpt-4o-mini"

    def test_llm_effective_model_uses_reorganize(self) -> None:
        cfg = LLMConfig(model="base", reorganize_model="reorg")
        assert cfg.effective_model == "reorg"

    def test_ocr_defaults(self) -> None:
        cfg = OCRConfig()
        assert cfg.mineru_api_key == ""
        assert (
            cfg.paddleocr_host == "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
        )
        assert cfg.paddleocr_model == "PaddleOCR-VL-1.6"
        assert cfg.glmocr_model == "glm-ocr"
        assert cfg.upload_batch_size == 1

    def test_moldet_defaults(self) -> None:
        cfg = MoldetConfig()
        assert cfg.device == "auto"
        assert cfg.auto_moldet_on_import is True
        assert cfg.detection_dpi == pytest.approx(200.0)
        assert cfg.detection_batch_size == 0
        assert cfg.text_page_char_threshold == 500
        assert cfg.max_pages_per_doc is None

    def test_ingest_defaults(self) -> None:
        cfg = IngestConfig()
        assert cfg.auto_enqueue_on_import is True
        assert cfg.default_priority == 0
        assert cfg.max_retries == 1

    def test_pdf_parse_defaults(self) -> None:
        cfg = PdfParseConfig()
        assert cfg.chunk_size == 1000
        assert cfg.chunk_overlap == 200

    def test_popo_defaults(self) -> None:
        cfg = PopoConfig()
        assert cfg.enabled is False

    def test_vlm_defaults(self) -> None:
        cfg = VLMConfig()
        assert cfg.provider == "openai_compatible"

    def test_app_config_defaults(self) -> None:
        cfg = AppConfig()
        assert cfg.theme == "dark"
        assert cfg.language == "zh-CN"
        assert isinstance(cfg.ocr, OCRConfig)
        assert isinstance(cfg.moldet, MoldetConfig)
        assert isinstance(cfg.ingest, IngestConfig)
        assert isinstance(cfg.pdf_parse, PdfParseConfig)
        assert isinstance(cfg.popo, PopoConfig)
        assert isinstance(cfg.vlm, VLMConfig)


class TestValidation:
    """Invalid types must raise ValidationError."""

    def test_invalid_temperature_type(self) -> None:
        with pytest.raises(ValidationError):
            LLMConfig(temperature="hot")

    def test_invalid_detection_dpi_type(self) -> None:
        with pytest.raises(ValidationError):
            MoldetConfig(detection_dpi="high")

    def test_app_config_rejects_unknown_top_level(self) -> None:
        # extra="ignore" means unknown top-level keys are silently dropped
        cfg = AppConfig(unknown_field="value")
        assert "unknown_field" not in cfg.model_dump()

    def test_app_config_ignores_environment_variables(self, monkeypatch) -> None:
        """Business settings must come from settings.json, never MBFORGE_* env vars."""
        monkeypatch.setenv("MBFORGE_THEME", "light")

        assert AppConfig().theme == "dark"


class TestDictDeserialization:
    """Legacy dict-shaped settings.json must deserialize correctly."""

    def test_app_config_from_nested_dict(self) -> None:
        data: dict[str, Any] = {
            "ocr": {
                "mineru_api_key": "mk",
                "upload_batch_size": 4,
            },
            "moldet": {
                "detection_dpi": 300.0,
                "detection_batch_size": 2,
            },
            "popo": {"enabled": True},
        }
        cfg = AppConfig.model_validate(data)
        assert cfg.ocr.mineru_api_key == "mk"
        assert cfg.ocr.upload_batch_size == 4
        assert cfg.moldet.detection_dpi == pytest.approx(300.0)
        assert cfg.moldet.detection_batch_size == 2
        assert cfg.popo.enabled is True

    def test_update_settings_deep_merge(self, monkeypatch, tmp_path) -> None:
        from mbforge.utils import config

        settings_path = tmp_path / "settings.json"
        monkeypatch.setattr(config, "_SETTINGS_PATH", settings_path)
        monkeypatch.setattr(config, "GLOBAL_APP_DIR", tmp_path)

        initial = AppConfig()
        initial.library_root = str(tmp_path)
        config.save_global_config(initial)

        new_cfg = update_settings(
            {
                "ocr": {"upload_batch_size": 8},
                "moldet": {"device": "cpu"},
            }
        )
        assert new_cfg.ocr.upload_batch_size == 8
        assert new_cfg.moldet.device == "cpu"
        # Other defaults preserved
        assert new_cfg.ocr.mineru_api_key == ""
        assert new_cfg.moldet.detection_dpi == pytest.approx(200.0)


class TestSecretRedaction:
    """GET /api/v1/settings must not leak credentials."""

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("api_key", "secret"),
            ("secret_token", "secret"),
            ("hf_key", "secret"),
            ("password", "secret"),
            ("auth_token", "secret"),
        ],
    )
    def test_secret_keys_redacted(self, key: str, value: str) -> None:
        assert _redact_secrets({key: value}) == {key: "***"}

    def test_non_secret_keys_preserved(self) -> None:
        assert _redact_secrets({"model": "gpt-4o", "host": "localhost"}) == {
            "model": "gpt-4o",
            "host": "localhost",
        }

    def test_nested_redaction(self) -> None:
        data = {
            "llm": {"api_key": "ak", "model": "m"},
            "ocr": {"paddleocr_api_key": "pk"},
        }
        redacted = _redact_secrets(data)
        assert redacted["llm"]["api_key"] == "***"
        assert redacted["llm"]["model"] == "m"
        assert redacted["ocr"]["paddleocr_api_key"] == "***"


def test_app_config_ignores_retired_project_settings() -> None:
    """Existing settings.json files must remain loadable after the cleanup."""
    cfg = AppConfig.model_validate(
        {
            "auto_open_project": True,
            "recent_projects": [{"root": "/tmp/library", "name": "Old library"}],
        }
    )

    assert "auto_open_project" not in cfg.model_dump()
    assert "recent_projects" not in cfg.model_dump()
