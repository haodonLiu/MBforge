"""Shared state for model server — replaces module-level globals in server.py."""

from __future__ import annotations

import time

# Model status tracking
_model_status: dict[str, str] = {
    "moldet": "loading",
    "molscribe": "loading",
}

# Resource cache
_resource_cache: dict[str, str] = {}
_resource_cache_time: float = 0.0
RESOURCE_CACHE_TTL = 60.0

# Failure cooldown
_last_failure: dict[str, float] = {}
RETRY_COOLDOWN = 30.0


def should_skip_cooldown(model_name: str) -> bool:
    """Check if we should skip health check due to recent failure."""
    last = _last_failure.get(model_name)
    if last is None:
        return False
    return (time.monotonic() - last) < RETRY_COOLDOWN


def mark_failure(model_name: str) -> None:
    """Record a failure timestamp for cooldown."""
    _last_failure[model_name] = time.monotonic()


def clear_failure(model_name: str) -> None:
    """Clear failure timestamp."""
    _last_failure.pop(model_name, None)


def set_model_status(name: str, status: str) -> None:
    """Update model status and clear failure if ready."""
    _model_status[name] = status
    if status == "ready":
        clear_failure(name)


def get_model_status() -> dict[str, str]:
    """Get current model statuses."""
    return _model_status.copy()


def get_resource_cache() -> tuple[dict[str, str], float]:
    """Get resource cache and timestamp."""
    return _resource_cache, _resource_cache_time


def set_resource_cache(cache: dict[str, str], timestamp: float) -> None:
    """Update resource cache."""
    global _resource_cache, _resource_cache_time
    _resource_cache = cache
    _resource_cache_time = timestamp
