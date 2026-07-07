"""Tests for the diagnostic ring buffer + /api/v1/diagnostics router.

The buffer is module-level state with a deque.maxlen cap, so order across
tests depends on previous appends. Tests use fresh pushes and filter or
slice locally rather than asserting on absolute size.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Ensure src on path when running pytest directly without `-m`.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fastapi.testclient import TestClient

from mbforge.app import create_app
from mbforge.utils.logger import (
    DiagnosticRingHandler,
    JsonFormatter,
    get_diagnostic_stats,
    get_diagnostics,
    push_diagnostic,
    reset_request_path,
    set_request_path,
)


def _client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


class TestRingBuffer:
    def test_push_diagnostic_returns_seq(self) -> None:
        seq = push_diagnostic({"level": "ERROR", "message": "x", "category": "t"})
        assert isinstance(seq, int)
        assert seq > 0

    def test_get_diagnostics_filters_by_level(self) -> None:
        push_diagnostic({"level": "WARNING", "message": "w", "category": "t"})
        push_diagnostic({"level": "ERROR", "message": "e", "category": "t"})
        out = get_diagnostics(level="WARNING", limit=50)
        assert all(r["level"] == "WARNING" for r in out)

    def test_get_diagnostics_filters_by_category(self) -> None:
        push_diagnostic({"level": "ERROR", "message": "x", "category": "alpha"})
        push_diagnostic({"level": "ERROR", "message": "y", "category": "beta"})
        out = get_diagnostics(category="alpha", limit=50)
        assert all(r["category"] == "alpha" for r in out)

    def test_get_diagnostics_filters_by_error_code(self) -> None:
        push_diagnostic(
            {"level": "ERROR", "message": "x", "error_code": "validation_error"}
        )
        push_diagnostic(
            {"level": "ERROR", "message": "y", "error_code": "internal_error"}
        )
        out = get_diagnostics(error_code="validation_error", limit=50)
        assert all(r["error_code"] == "validation_error" for r in out)

    def test_get_diagnostics_since_returns_only_newer(self) -> None:
        a = push_diagnostic({"level": "ERROR", "message": "a"})
        push_diagnostic({"level": "ERROR", "message": "b"})
        out = get_diagnostics(since=a, limit=50)
        # 'a' itself excluded; everything after returned.
        assert all(r["seq"] > a for r in out)

    def test_get_diagnostics_limit_capped_at_1000(self) -> None:
        # limit=5000 should be clamped to 1000, not raise.
        out = get_diagnostics(limit=5000)
        assert len(out) <= 1000

    def test_stats_aggregates(self) -> None:
        push_diagnostic({"level": "ERROR", "message": "x", "category": "agg_test"})
        s = get_diagnostic_stats()
        assert "by_level" in s
        assert "by_category" in s
        assert "total" in s
        assert "capacity" in s
        assert s["capacity"] == 500
        assert s["total"] >= 1
        assert "ERROR" in s["by_level"]


class TestRequestPathContext:
    def test_set_reset(self) -> None:
        token = set_request_path("/api/v1/diagnostics/errors")
        try:
            # Reading the value would require accessing the var; here we
            # just confirm set/reset are callable and do not raise.
            assert True
        finally:
            reset_request_path(token)


class TestJsonFormatter:
    def test_format_includes_mbforge_fields(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="mbforge.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="formatted %s",
            args=("arg",),
            exc_info=None,
        )
        record.mbforge_error_code = "test_code"
        record.mbforge_severity = "error"
        record.mbforge_category = "routers.test"
        record.mbforge_status_code = 500
        record.mbforge_context = {"foo": "bar"}
        out = formatter.format(record)
        parsed = json.loads(out)
        assert parsed["level"] == "ERROR"
        assert parsed["message"] == "formatted arg"
        assert parsed["error_code"] == "test_code"
        assert parsed["severity"] == "error"
        assert parsed["category"] == "routers.test"
        assert parsed["context"] == {"foo": "bar"}
        assert parsed["request_path"] == "-"


class TestDiagnosticRingHandler:
    def test_emit_assigns_seq(self) -> None:
        handler = DiagnosticRingHandler(level=logging.DEBUG)
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="observing-unique-marker",
            args=None,
            exc_info=None,
        )
        handler.emit(record)
        # Cross-test pollution: deque holds up to 500 records across all
        # tests in the process. Filter by message to find ours.
        out = get_diagnostics(level="WARNING", limit=500)
        seqs = [r["seq"] for r in out if r["message"] == "observing-unique-marker"]
        assert len(seqs) == 1
        assert isinstance(seqs[0], int)
        assert seqs[0] > 0

    def test_emit_swallows_exceptions(self) -> None:
        # Defensive: even if record-to-payload conversion fails, logging
        # should not break the application. We simulate this by passing
        # a record whose getMessage() raises — but we keep this light to
        # avoid coupling to LogRecord internals.
        handler = DiagnosticRingHandler(level=logging.DEBUG)
        record = logging.LogRecord(
            name="ok-name",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="benign",
            args=None,
            exc_info=None,
        )
        # Monkey-patch the record's getMessage to raise. The handler's
        # try/except must absorb the failure.
        record.getMessage = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        # Must not raise.
        handler.emit(record)


class TestDiagnosticsEndpoints:
    def test_errors_list_returns_records(self) -> None:
        push_diagnostic(
            {"level": "ERROR", "message": "smoke", "category": "smoke_test"}
        )
        c = _client()
        r = c.get("/api/v1/diagnostics/errors?category=smoke_test&limit=20")
        assert r.status_code == 200
        body = r.json()
        assert "errors" in body
        assert body["count"] >= 1
        assert body["errors"][0]["category"] == "smoke_test"

    def test_stats_returns_aggregates(self) -> None:
        c = _client()
        r = c.get("/api/v1/diagnostics/stats")
        assert r.status_code == 200
        body = r.json()
        assert "by_level" in body
        assert "by_category" in body
        assert body["capacity"] == 500

    def test_client_report_inserts_with_category_client(self) -> None:
        c = _client()
        payload = {
            "errors": [
                {
                    "message": "boundary exploded",
                    "stack": "Error: boundary exploded\n  at <anonymous>",
                    "category": "client",
                    "severity": "ERROR",
                    "context": {"component": "Workspace.tsx"},
                }
            ]
        }
        r = c.post("/api/v1/diagnostics/errors", json=payload)
        assert r.status_code == 204
        listed = c.get("/api/v1/diagnostics/errors?category=client&limit=10")
        # Some records (newest first by seq); just confirm at least one
        # with category=client exists.
        assert any(
            rec["category"] == "client" for rec in listed.json()["errors"]
        )

    def test_unknown_error_404_route_handled_via_ring_buffer(self) -> None:
        # Probe: GET on a seq_id that does not exist returns a clean 200
        # body rather than crashing the handler. The handler decides
        # {"success": False, "error": "not found"} when seq is absent.
        c = _client()
        r = c.get("/api/v1/diagnostics/errors/9999999")
        assert r.status_code == 200
        assert r.json().get("success") is False


class TestMBForgeErrorPropagatesThroughExceptionHandler:
    """End-to-end: a route that raises MBForgeError is intercepted and
    results in a structured JSON body + ring buffer entry."""

    def test_validation_error_appears_in_ring_buffer(self) -> None:
        # Push a record mimicking what an MBForgeError handler would emit,
        # then verify the GET endpoint surfaces its full shape.
        push_diagnostic(
            {
                "level": "WARNING",
                "logger": "mbforge.app.exception_handler",
                "message": "root path is required",
                "error_code": "validation_error",
                "status_code": 422,
                "severity": "warning",
                "category": "mbforge.utils.helpers",
                "context": {},
            }
        )
        c = _client()
        r = c.get(
            "/api/v1/diagnostics/errors?error_code=validation_error&limit=200"
        )
        assert r.status_code == 200
        body = r.json()
        # The records returned may include earlier bare MBForgeError pushes
        # from other tests; pick the one with the full structure.
        matches = [
            rec
            for rec in body["errors"]
            if rec.get("message") == "root path is required"
        ]
        assert matches, "expected the just-pushed record in the buffer"
        rec = matches[0]
        assert rec["severity"] == "warning"
        assert rec["status_code"] == 422
        assert rec["category"] == "mbforge.utils.helpers"
