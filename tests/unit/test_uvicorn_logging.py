from __future__ import annotations

import logging

import pytest

from mbforge.utils.logger import UvicornAccessLogFilter


def _access_record(status_code: int | None) -> logging.LogRecord:
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request",
        args=(),
        exc_info=None,
    )
    if status_code is not None:
        record.status_code = status_code
    return record


@pytest.mark.parametrize("status_code", [200, 201, 204, 299])
def test_successful_access_records_are_filtered(status_code: int) -> None:
    assert not UvicornAccessLogFilter().filter(_access_record(status_code))


@pytest.mark.parametrize("status_code", [100, 301, 400, 404, 500])
def test_non_success_access_records_are_kept(status_code: int) -> None:
    assert UvicornAccessLogFilter().filter(_access_record(status_code))


def test_access_record_without_status_code_is_kept() -> None:
    assert UvicornAccessLogFilter().filter(_access_record(None))
