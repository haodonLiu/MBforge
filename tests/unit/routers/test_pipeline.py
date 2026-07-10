"""Unit tests for the pipeline router's SSE endpoint."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mbforge.core.database import DatabaseManager


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Create a TestClient for the FastAPI app.

    Startup pre-warming is patched to avoid slow model downloads during tests.
    """
    import mbforge.server as _server
    import mbforge.utils.helpers as _helpers

    _orig_prewarm = getattr(_server, "_prewarm", lambda: None)
    _orig_check_environment = getattr(_helpers, "check_environment", lambda: None)

    def _noop() -> None:
        return None

    _server._prewarm = _noop
    _helpers.check_environment = _noop

    try:
        from mbforge.app import create_app

        app = create_app()
        c = TestClient(app)
        yield c
    finally:
        c.close()
        _server._prewarm = _orig_prewarm
        _helpers.check_environment = _orig_check_environment


def _parse_sse(body: bytes) -> list[dict]:
    """Parse a simple text/event-stream body into payload dicts."""
    events: list[dict] = []
    current: dict[str, str] = {}
    for line in body.decode("utf-8").splitlines():
        if line.startswith("event: "):
            current["event"] = line[len("event: ") :]
        elif line.startswith("data: "):
            current["data"] = line[len("data: ") :]
        elif line == "" and current:
            events.append(json.loads(current["data"]))
            current = {}
    if current:
        events.append(json.loads(current["data"]))
    return events


def test_pipeline_events_stream_returns_log_rows(
    client: TestClient, tmp_path: Path
) -> None:
    """The SSE endpoint yields persisted ingest_logs rows with structured data."""
    root = tmp_path / "library"
    root.mkdir(parents=True, exist_ok=True)
    db = DatabaseManager.get(str(root))
    db.initialize()

    task_id = "task-sse-1"
    with db.kb_conn() as conn:
        conn.execute(
            "INSERT INTO ingest_queue (id, file_path, status) VALUES (?, ?, ?)",
            (task_id, str(root / "doc.pdf"), "pending"),
        )
        conn.execute(
            """
            INSERT INTO ingest_logs
                (doc_id, stage, level, message, ts_ms, task_id, data)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "doc-1",
                "detect",
                "info",
                "Detected 2 molecules",
                1234567890000,
                task_id,
                json.dumps({"molecule_count": 2}),
            ),
        )

    response = client.get(
        f"/api/v1/pipeline/events/{task_id}",
        params={"library_root": str(root)},
        timeout=10,
    )
    assert response.status_code == 200
    events = _parse_sse(response.content)

    assert len(events) >= 1
    payload = events[0]
    assert payload["stage"] == "detect"
    assert payload["event"] == "info"
    assert payload["message"] == "Detected 2 molecules"
    assert payload["ts_ms"] == 1234567890000
    assert payload["data"] == {"molecule_count": 2}
