"""Tests for MBForgeError severity/category/context extensions.

The original two-arg signature must keep working for every existing raise
site (library.py, helpers.validate_path, server.py). The new fields surface
via __init__ keyword args and default sensibly.
"""

from __future__ import annotations

from mbforge.utils.helpers import (
    MBForgeError,
    PathTraversalError,
    ValidationError,
    http_status_to_severity,
)


class TestMBForgeError:
    def test_default_severity_is_error(self) -> None:
        exc = MBForgeError("boom")
        assert exc.severity == "error"
        assert exc.message == "boom"
        assert exc.detail is None

    def test_default_category_is_class_module(self) -> None:
        # Default category is the module where the *concrete subclass* was
        # defined, not where the raise statement lives. Subclasses can
        # always override via the `category=` keyword.
        v = ValidationError("bad input")
        assert v.category == "mbforge.utils.helpers"

    def test_subclass_can_override_category(self) -> None:
        v = ValidationError(
            "bad input", category="routers.notes", context={"field": "root"}
        )
        assert v.category == "routers.notes"
        assert v.context == {"field": "root"}

    def test_explicit_severity_override(self) -> None:
        exc = MBForgeError("warn", severity="warning", category="routers.test")
        assert exc.severity == "warning"
        assert exc.category == "routers.test"

    def test_context_round_trip(self) -> None:
        ctx = {"doc_id": "abc", "page": 3}
        exc = MBForgeError("ctx", context=ctx)
        assert exc.context == ctx

    def test_subclass_inherits_extended_signature(self) -> None:
        # ValidationError status_code 422, severity defaults to error.
        v = ValidationError("bad input")
        assert v.status_code == 422
        assert v.error_code == "validation_error"
        assert v.severity == "error"

    def test_path_traversal_keeps_existing_behavior(self) -> None:
        p = PathTraversalError("escaped")
        assert p.status_code == 403
        assert p.error_code == "path_traversal"

    def test_two_positional_arg_form_still_compiles(self) -> None:
        # Back-compat: callers that pass only positional args must still work.
        exc = MBForgeError("legacy message")
        assert exc.detail is None
        assert exc.context == {}


class TestHttpStatusToSeverity:
    def test_warning_band(self) -> None:
        assert http_status_to_severity(400) == "warning"
        assert http_status_to_severity(422) == "warning"
        assert http_status_to_severity(403) == "warning"

    def test_info_band(self) -> None:
        assert http_status_to_severity(404) == "info"

    def test_error_band(self) -> None:
        assert http_status_to_severity(500) == "error"
        assert http_status_to_severity(503) == "error"

    def test_unknown_status_falls_back_to_error(self) -> None:
        # Anything outside the table should map to "error" rather than crash.
        assert http_status_to_severity(418) == "error"
        assert http_status_to_severity(999) == "error"
