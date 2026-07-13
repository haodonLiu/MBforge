"""Unit tests for molecule rendering endpoints."""

from __future__ import annotations

import asyncio

import pytest

from mbforge.routers.render import _render_molecule_sync, render_molecule


def test_render_molecule_offloads_to_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    """The render route delegates RDKit/PIL drawing to asyncio.to_thread."""
    calls: list[tuple[object, tuple, dict]] = []

    async def _fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return {"_fake": True}

    monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

    result = asyncio.run(render_molecule({"smiles": "CCO", "width": 200}))

    assert result == {"_fake": True}
    assert len(calls) == 1
    assert calls[0][0] is _render_molecule_sync
    assert calls[0][1] == ("CCO", 200, 200)


def test_render_molecule_rejects_empty_smiles_at_route_level() -> None:
    """Empty input is rejected before any thread offload."""
    result = asyncio.run(render_molecule({"smiles": ""}))
    assert result == {"success": False, "error": "smiles required"}
