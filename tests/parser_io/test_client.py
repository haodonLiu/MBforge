import pytest
from unittest.mock import Mock, patch
from mbforge.parser_io.client import ParserClient
from mbforge.parser_io.config import ParserConfig
from mbforge.parser_io.models import ParseResult


@pytest.fixture
def mock_config():
    return ParserConfig(host="https://uniparser.example.com", api_key="test-key")


def test_parser_client_init(mock_config):
    """验证 ParserClient 保存配置."""
    with patch("mbforge.parser_io.client.UniParserClientBase", create=True):
        client = ParserClient(mock_config)
        assert client.config.host == "https://uniparser.example.com"
        assert client.config.api_key == "test-key"


@patch("mbforge.parser_io.client.UniParserClientBase", create=True)
def test_parse_pdf_calls_underlying_client(MockUniParser, mock_config):
    mock_instance = MockUniParser.return_value
    mock_instance.trigger_file.return_value = {
        "status": "success",
        "token": "test-token-123",
    }

    client = ParserClient(mock_config)
    result = client.parse_pdf("test.pdf")

    assert result.status == "success"
    assert result.token == "test-token-123"
    mock_instance.trigger_file.assert_called_once()


@patch("mbforge.parser_io.client.UniParserClientBase", create=True)
def test_get_result_returns_raw_data(MockUniParser, mock_config):
    mock_instance = MockUniParser.return_value
    mock_instance.get_result.return_value = {
        "status": "success",
        "data": {"content": "test content"},
    }

    client = ParserClient(mock_config)
    raw = client.get_result("some-token")

    assert raw["status"] == "success"
    assert "data" in raw


@patch("mbforge.parser_io.client.UniParserClientBase", create=True)
def test_parse_and_wait_sync_mode(MockUniParser, mock_config):
    mock_instance = MockUniParser.return_value
    mock_instance.trigger_file.return_value = {"status": "success", "token": "sync-token"}
    mock_instance.get_result.return_value = {
        "status": "completed",
        "data": {"result": "done"},
    }

    client = ParserClient(mock_config)
    result = client.parse_and_wait("sync.pdf")

    assert result.token == "sync-token"
