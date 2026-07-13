"""Unit tests for the models management router."""

from __future__ import annotations

import asyncio

import pytest

from mbforge.routers.models_router import (
    _render_molecule_sync,
    _test_model_sync,
    render_molecule,
)
from mbforge.routers.models_router import (
    test_model as model_test_handler,
)


def _capture_to_thread(monkeypatch: pytest.MonkeyPatch):
    """Patch asyncio.to_thread so callers can inspect what was offloaded."""
    calls: list[tuple[object, tuple, dict]] = []

    async def _fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return {"_fake": True}

    monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)
    return calls


def test_test_model_offloads_to_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    """The model-test route delegates blocking inference to asyncio.to_thread."""
    calls = _capture_to_thread(monkeypatch)

    result = asyncio.run(model_test_handler({"model_id": "molscribe"}))

    assert result == {"success": True, "_fake": True}
    assert len(calls) == 1
    assert calls[0][0] is _test_model_sync


def test_render_molecule_offloads_to_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    """The render route delegates RDKit/PIL drawing to asyncio.to_thread."""
    calls = _capture_to_thread(monkeypatch)

    result = asyncio.run(render_molecule({"smiles": "CCO", "width": 200, "height": 150}))

    assert result == {"_fake": True}
    assert len(calls) == 1
    assert calls[0][0] is _render_molecule_sync
    assert calls[0][1] == ("CCO", 200, 150)
