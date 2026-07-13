"""Unit tests for chemistry endpoints."""

from __future__ import annotations

import asyncio

import pytest

from mbforge.routers.chem import (
    _canonicalize_sync,
    _fingerprint_sync,
    _properties_sync,
    _tanimoto_sync,
    _validate_smiles_sync,
    canonicalize,
    fingerprint,
    properties,
    tanimoto,
    validate_smiles,
)


def _capture_to_thread(monkeypatch: pytest.MonkeyPatch):
    """Patch asyncio.to_thread so callers can inspect what was offloaded."""
    calls: list[tuple[object, tuple, dict]] = []

    async def _fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return {"_fake": True}

    monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)
    return calls


@pytest.mark.parametrize(
    "handler, sync_func, body",
    [
        (validate_smiles, _validate_smiles_sync, {"smiles": "CCO"}),
        (fingerprint, _fingerprint_sync, {"smiles": "CCO"}),
        (properties, _properties_sync, {"smiles": "CCO"}),
        (canonicalize, _canonicalize_sync, {"smiles": "CCO"}),
        (
            tanimoto,
            _tanimoto_sync,
            {"fingerprint_a": [1, 0, 1], "fingerprint_b": [1, 1, 0]},
        ),
    ],
)
def test_chem_routes_offload_to_thread(
    monkeypatch: pytest.MonkeyPatch,
    handler,
    sync_func,
    body: dict,
) -> None:
    """Async chemistry routes delegate blocking RDKit work to asyncio.to_thread."""
    calls = _capture_to_thread(monkeypatch)

    result = asyncio.run(handler(body))

    assert result == {"_fake": True}
    assert len(calls) == 1
    assert calls[0][0] is sync_func
