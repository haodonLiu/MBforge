# tests/parser_io/test_config.py
import pytest
from mbforge.parser_io.config import ParserConfig, load_config, validate_config


def test_parser_config_dataclass():
    config = ParserConfig(host="https://example.com", api_key="test-key")
    assert config.host == "https://example.com"
    assert config.api_key == "test-key"


def test_validate_config_success():
    config = ParserConfig(host="https://example.com", api_key="test-key")
    assert validate_config(config) is True


def test_validate_config_empty_host():
    config = ParserConfig(host="", api_key="test-key")
    assert validate_config(config) is False


def test_validate_config_empty_api_key():
    config = ParserConfig(host="https://example.com", api_key="")
    assert validate_config(config) is False


def test_validate_config_missing_protocol():
    config = ParserConfig(host="example.com", api_key="test-key")
    assert validate_config(config) is False


def test_validate_config_no_scheme():
    """host 必须以 http:// 或 https:// 开头"""
    config = ParserConfig(host="example.com", api_key="test-key")
    assert validate_config(config) is False
