"""Unit tests for the /api/v1/extract/activities HTTP endpoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from mbforge.app import create_app
from mbforge.pipeline.extract_activities import ActivityRecord


def _fake_record() -> ActivityRecord:
    return ActivityRecord(
        activity_type="IC50",
        value=12.5,
        value_original=12.5,
        unit="nM",
        operator="=",
        target="EGFR",
        assay_type="enzymatic",
        raw_text="| 1 | 12.5 |",
        confidence=0.9,
        page_num=None,
        evidence_kind="table",
        evidence_bbox=None,
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_extract_activities_endpoint_returns_records(client: TestClient) -> None:
    """The /extract/activities endpoint returns a list of dicts with
    activity_type/value/units when the LLM parser yields a record."""
    with patch(
        "mbforge.pipeline.extract_activities._parse_table_with_llm",
        return_value=[_fake_record()],
    ):
        resp = client.post(
            "/api/v1/extract/activities",
            json={"text": "| Cmpd | IC50 (nM) |\n|---|---|\n| 1 | 10 |\n"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["activity_type"] == "IC50"
    assert body[0]["value"] == 12.5
    assert body[0]["units"] == "nM"


def test_extract_activities_endpoint_empty_text(client: TestClient) -> None:
    """Empty input returns an empty list (no LLM call)."""
    resp = client.post("/api/v1/extract/activities", json={"text": ""})
    assert resp.status_code == 200
    assert resp.json() == []


def test_extract_activities_endpoint_no_tables(client: TestClient) -> None:
    """Text without markdown tables returns an empty list."""
    resp = client.post(
        "/api/v1/extract/activities",
        json={"text": "Just some prose, no tables here."},
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_extract_activities_endpoint_handles_llm_failure(
    client: TestClient,
) -> None:
    """When the LLM call raises, the endpoint returns [] (degrade, no 500)."""
    with patch(
        "mbforge.pipeline.extract_activities._parse_table_with_llm",
        side_effect=RuntimeError("model down"),
    ):
        resp = client.post(
            "/api/v1/extract/activities",
            json={"text": "| A | B |\n|---|---|\n| 1 | 2 |\n"},
        )
    assert resp.status_code == 200
    assert resp.json() == []
