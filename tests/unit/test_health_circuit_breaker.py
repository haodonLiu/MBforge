"""Health endpoint circuit-breaker tests."""

from __future__ import annotations

import importlib
import time
from unittest.mock import patch


def test_circuit_breaker_skips_after_failure():
    """Model init fails → 30s cooldown skips retry."""
    server = importlib.import_module("mbforge.server")
    importlib.reload(server)

    server._last_failure.clear()
    server._model_status["embedder"] = "loading"

    call_count = {"n": 0}

    def _failing_load():
        call_count["n"] += 1
        raise RuntimeError("model not loaded")

    with patch.object(server.qwen3_embed, "load", _failing_load):
        import asyncio
        asyncio.run(server.health_check())
        assert call_count["n"] == 1, "first call should invoke load"
        assert server._model_status["embedder"] == "error"
        assert "embedder" in server._last_failure

        asyncio.run(server.health_check())
        assert call_count["n"] == 1, "second call should be skipped by circuit breaker"

    server._last_failure["embedder"] = time.monotonic() - 31.0
    with patch.object(server.qwen3_embed, "load", _failing_load):
        import asyncio
        asyncio.run(server.health_check())
        assert call_count["n"] == 2, "after cooldown, should retry"


def test_circuit_breaker_clears_on_success():
    """Success clears failure timestamp."""
    server = importlib.import_module("mbforge.server")
    importlib.reload(server)

    server._last_failure["embedder"] = time.monotonic() - 100.0
    server._model_status["embedder"] = "error"

    server._clear_failure("embedder")
    assert "embedder" not in server._last_failure

    server._last_failure["embedder"] = time.monotonic() - 100.0
    if not server._should_skip_due_to_cooldown("embedder"):
        try:
            server._model_status["embedder"] = "ready"
            server._clear_failure("embedder")
        except Exception:
            pass
    assert server._model_status["embedder"] == "ready"
    assert "embedder" not in server._last_failure


def test_set_model_status_clears_failure():
    """External ready status clears circuit breaker."""
    server = importlib.import_module("mbforge.server")
    server._last_failure["reranker"] = time.monotonic()
    server.set_model_status("reranker", "ready")
    assert "reranker" not in server._last_failure
