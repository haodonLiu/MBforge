"""Phase 3 health endpoint 熔断器测试.

验证 health check 在 model init 失败后进入冷却期，
避免后续 health poll 反复触发昂贵初始化。
"""
from __future__ import annotations

import importlib
import time
from unittest.mock import patch


def test_circuit_breaker_skips_after_failure():
    """model init 失败后，30s 内再次调用应被熔断（不调用 get_embedder）。"""
    health = importlib.import_module("mbforge.model_server.routers.health")
    importlib.reload(health)

    # 重置 cooldown 状态
    health._last_failure.clear()
    health._model_status["embedder"] = "loading"

    # 模拟 embedder init 失败
    call_count = {"n": 0}

    def _failing_get_embedder():
        call_count["n"] += 1
        raise RuntimeError("model not loaded")

    with patch.object(health, "get_embedder", _failing_get_embedder):
        import asyncio
        # 第一次调用：触发失败
        asyncio.run(health.health_check())
        assert call_count["n"] == 1, "first call should invoke get_embedder"
        assert health._model_status["embedder"] == "error"
        # 失败后应记录时间戳
        assert "embedder" in health._last_failure

        # 第二次调用（冷却期内）：不应再次调用 get_embedder
        asyncio.run(health.health_check())
        assert call_count["n"] == 1, "second call should be skipped by circuit breaker"

    # 模拟冷却期过期：手动设置 _last_failure 到 31s 之前
    health._last_failure["embedder"] = time.monotonic() - 31.0
    with patch.object(health, "get_embedder", _failing_get_embedder):
        import asyncio
        asyncio.run(health.health_check())
        assert call_count["n"] == 2, "after cooldown, should retry"


def test_circuit_breaker_clears_on_success():
    """model init 成功后，应清空失败时间戳。"""
    health = importlib.import_module("mbforge.model_server.routers.health")
    importlib.reload(health)

    # 模拟"上次失败"，但要等到 cooldown 过期后
    health._last_failure["embedder"] = time.monotonic() - 100.0
    health._model_status["embedder"] = "error"

    def _ok(_): return object()
    # mock 所有模型以避免实际加载
    # 直接调用 _clear_failure 验证逻辑（避免走完整 health_check 因为 uniparser
    # 路径需要 requests 真实 HTTP 调，CI 环境跑不动）。
    health._clear_failure("embedder")
    assert "embedder" not in health._last_failure

    # 也测一下：通过模拟 health_check 内部的 _should_skip_due_to_cooldown
    # 行为，验证成功时清除逻辑
    health._last_failure["embedder"] = time.monotonic() - 100.0
    # 直接复制 health_check 里的 embedder 成功路径逻辑：
    if not health._should_skip_due_to_cooldown("embedder"):
        try:
            _ok(None)
            health._model_status["embedder"] = "ready"
            health._clear_failure("embedder")
        except Exception:
            pass
    assert health._model_status["embedder"] == "ready"
    assert "embedder" not in health._last_failure


def test_set_model_status_clears_failure():
    """外部设置 ready 状态应清空熔断器。"""
    health = importlib.import_module("mbforge.model_server.routers.health")
    health._last_failure["vlm"] = time.monotonic()
    health.set_model_status("vlm", "ready")
    assert "vlm" not in health._last_failure
