"""Tests for settings secret redaction."""
from unittest.mock import patch
from mbforge.routers.settings import _redact_secrets, settings_get


def test_redact_api_keys():
    raw = {
        "ocr": {
            "mineru_api_key": "secret123",
            "paddleocr_api_key": "secret456",
            "glmocr_api_key": "secret789",
            "host": "https://example.com",
        },
        "llm": {"openai_api_key": "sk-xxx", "model": "gpt-4"},
        "theme": "dark",
    }
    redacted = _redact_secrets(raw)
    assert redacted["ocr"]["mineru_api_key"] == "***"
    assert redacted["ocr"]["paddleocr_api_key"] == "***"
    assert redacted["ocr"]["glmocr_api_key"] == "***"
    assert redacted["ocr"]["host"] == "https://example.com"
    assert redacted["llm"]["openai_api_key"] == "***"
    assert redacted["llm"]["model"] == "gpt-4"
    assert redacted["theme"] == "dark"


def test_redact_handles_non_string_secrets():
    assert _redact_secrets({"api_key": None}) == {"api_key": None}
    assert _redact_secrets({"api_key": 123}) == {"api_key": 123}
