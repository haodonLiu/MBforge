"""Smoke tests for all registered FastAPI routers.

Goal: ensure every router can be imported and responds to at least one endpoint
without raising an unhandled 500. We do not assert deep business logic here.
"""

from __future__ import annotations

from concurrent.futures import CancelledError
from contextlib import suppress

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Create a TestClient for the FastAPI app.

    Startup pre-warming is patched to avoid slow model downloads during tests.
    """
    # Patch heavy startup routines before importing the app.
    import mbforge.server as _server
    import mbforge.utils.helpers as _helpers

    _orig_prewarm = getattr(_server, "_prewarm", lambda: None)
    _orig_check_environment = getattr(_helpers, "check_environment", lambda: None)

    def _noop() -> None:
        return None

    _server._prewarm = _noop
    _helpers.check_environment = _noop

    c = None
    try:
        from mbforge.app import create_app

        app = create_app()
        c = TestClient(app)
        yield c
    finally:
        if c is not None:
            with suppress(CancelledError, RuntimeError):
                c.close()
        _server._prewarm = _orig_prewarm
        _helpers.check_environment = _orig_check_environment


# One representative endpoint per router registered in app.py.
# Format: (method, path, request_body_or_query, expected_status_in)
ROUTES: list[tuple[str, str, dict | None, tuple[int, ...]]] = [
    # health (mounted at /api/v1)
    ("GET", "/api/v1/health", None, (200,)),
    # library
    ("GET", "/api/v1/library/status", None, (200,)),
    # documents
    ("POST", "/api/v1/documents/list", {}, (200,)),
    # pipeline
    ("GET", "/api/v1/pipeline/worker/status", None, (200,)),
    # kb
    ("POST", "/api/v1/kb/search", {}, (200, 422)),
    # molecule
    ("POST", "/api/v1/molecule/list", {}, (200, 422)),
    # agent
    ("POST", "/api/v1/agent/init", {}, (200, 422)),
    # chem
    ("POST", "/api/v1/chem/validate-smiles", {}, (200, 422)),
    # coref
    ("POST", "/api/v1/coref/figure-labels", {}, (200, 422)),
    # detection-cache
    ("POST", "/api/v1/detection-cache/stats", {}, (200, 422)),
    # notes
    ("POST", "/api/v1/notes/list", {}, (200, 422)),
    # settings
    ("GET", "/api/v1/settings", None, (200,)),
    # resource
    ("POST", "/api/v1/resource/cache-dir-info", {}, (200, 422)),
    # pdf
    ("POST", "/api/v1/pdf/classify", {}, (200, 422)),
    # sar
    ("POST", "/api/v1/sar/find-scaffold", {}, (200,)),
    # ocr
    ("GET", "/api/v1/ocr/chain-status", None, (200,)),
    # diagnostics
    ("GET", "/api/v1/diagnostics/stats", None, (200,)),
    # moldet
    ("POST", "/api/v1/moldet/coref_ft", {}, (200, 422)),
]


@pytest.mark.parametrize("method, path, payload, expected_status", ROUTES)
def test_router_endpoint_responds(
    client: TestClient,
    method: str,
    path: str,
    payload: dict | None,
    expected_status: tuple[int, ...],
) -> None:
    """Each registered router should serve its representative endpoint without 500."""
    if method == "GET":
        response = client.get(path)
    elif method == "POST":
        response = client.post(path, json=payload or {})
    else:
        pytest.fail(f"Unsupported method: {method}")

    assert response.status_code in expected_status, (
        f"{method} {path} returned {response.status_code}: {response.text}"
    )


def test_events_router_is_registered(client: TestClient) -> None:
    """The SSE stream endpoint is registered; we avoid opening the infinite stream."""
    paths = {r.path for r in client.app.routes if hasattr(r, "path")}
    assert "/api/v1/events/stream" in paths
