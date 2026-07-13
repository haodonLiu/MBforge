"""Unit tests for agent tools."""

from __future__ import annotations

import asyncio

import pytest

from mbforge.agent.tools import (
    _compute_molecule_properties_sync,
    compute_molecule_properties,
)


def test_compute_molecule_properties_offloads_rdkit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The molecule-properties tool runs RDKit work off the event loop."""
    calls: list[tuple[object, tuple, dict]] = []

    async def _fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return '{"_fake": true}'

    monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

    result = asyncio.run(compute_molecule_properties.ainvoke({"smiles": "CCO"}))

    assert result == '{"_fake": true}'
    assert len(calls) == 1
    assert calls[0][0] is _compute_molecule_properties_sync
    assert calls[0][1] == ("CCO",)
