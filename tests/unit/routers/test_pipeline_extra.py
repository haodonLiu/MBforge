"""Additional unit tests for pipeline router async hygiene."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from mbforge.core.database import DatabaseManager
from mbforge.models.pipeline import (
    PipelineEnqueueRequest,
    PipelineQueueRequest,
)
from mbforge.routers.pipeline import (
    pipeline_enqueue,
    pipeline_queue,
    pipeline_queue_stats,
)
from mbforge.utils import config


def _capture_to_thread(monkeypatch: pytest.MonkeyPatch):
    """Patch asyncio.to_thread so callers can inspect what was offloaded."""
    calls: list[tuple[object, tuple, dict]] = []

    async def _fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return []

    monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)
    return calls


def _patch_config_root(monkeypatch: pytest.MonkeyPatch, root: str) -> None:
    """Point load_global_config at ``root`` so path validation succeeds."""
    original_load = config.load_global_config

    def _patched_load():
        cfg = original_load()
        cfg.library_root = root
        return cfg

    monkeypatch.setattr(config, "load_global_config", _patched_load)


def test_pipeline_queue_offloads_sqlite_to_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The /queue route must not run SQLite queries on the event loop."""
    calls = _capture_to_thread(monkeypatch)

    root = str(tmp_path / "library")
    Path(root).mkdir(parents=True, exist_ok=True)
    _patch_config_root(monkeypatch, root)
    db = DatabaseManager.get(root)
    db.initialize()

    result = asyncio.run(pipeline_queue(PipelineQueueRequest(library_root=root)))

    assert result.success is True
    assert result.tasks == []
    assert len(calls) == 1


def test_pipeline_queue_stats_offloads_sqlite_to_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The /queue/stats route must not run SQLite queries on the event loop."""
    calls = _capture_to_thread(monkeypatch)

    root = str(tmp_path / "library")
    Path(root).mkdir(parents=True, exist_ok=True)
    _patch_config_root(monkeypatch, root)
    db = DatabaseManager.get(root)
    db.initialize()

    result = asyncio.run(pipeline_queue_stats(PipelineQueueRequest(library_root=root)))

    assert result.success is True
    assert result.stats == {}
    assert len(calls) == 1


def test_pipeline_enqueue_unresolved_offloads_scan_and_sqlite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The enqueue_unresolved action offloads file scanning and DB work."""
    calls: list[tuple[object, tuple, dict]] = []

    async def _fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        # The second to_thread call runs the DB enqueue batch and should return an int.
        if func.__name__ == "_enqueue_all":
            return 0
        return []

    monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

    root = str(tmp_path / "library")
    Path(root).mkdir(parents=True, exist_ok=True)
    _patch_config_root(monkeypatch, root)
    db = DatabaseManager.get(root)
    db.initialize()

    with patch("mbforge.routers.pipeline._background_futures", {}):
        result = asyncio.run(
            pipeline_enqueue(
                PipelineEnqueueRequest(library_root=root, action="enqueue_unresolved")
            )
        )

    assert result.success is True
    assert result.enqueued == 0
    # First to_thread call is scan_library_files, second is the DB enqueue batch.
    assert len(calls) == 2
