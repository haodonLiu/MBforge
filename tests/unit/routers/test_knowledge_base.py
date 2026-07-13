from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


def test_kb_search_missing_params(app_client: TestClient) -> None:
    resp = app_client.post("/api/v1/kb/search", json={})
    assert resp.status_code == 200
    assert resp.json()["success"] is False


def test_kb_search_with_mocked_adapter(app_client: TestClient, tmp_library) -> None:
    with patch("mbforge.core.knowledge_base.search") as mock_search:
        mock_search.return_value = {
            "results": [{"doc_id": "d1", "text": "result"}],
            "answer": "",
            "count": 1,
            "from_cache": False,
        }
        resp = app_client.post(
            "/api/v1/kb/search",
            json={"query": "q", "library_root": str(tmp_library)},
        )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert len(resp.json()["results"]) == 1


def test_kb_pages_missing_params(app_client: TestClient) -> None:
    resp = app_client.post("/api/v1/kb/pages", json={})
    assert resp.status_code == 200
    assert resp.json()["success"] is False


def test_kb_wiki_list_empty(app_client: TestClient, tmp_library) -> None:
    resp = app_client.get(f"/api/v1/kb/wiki/list?library_root={tmp_library}")
    assert resp.status_code == 200
    assert resp.json()["summaries"] == []


def test_kb_wiki_summary_uses_resolved_root(
    app_client: TestClient, tmp_library: Path
) -> None:
    """The wiki endpoint must resolve library_root before building paths."""
    summary = tmp_library / ".mbforge" / "openkb" / "wiki" / "summaries" / "doc1.md"
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text("# Summary", encoding="utf-8")

    resp = app_client.get(
        "/api/v1/kb/wiki/summary",
        params={
            "doc_id": "doc1",
            "library_root": str(tmp_library / ".." / tmp_library.name),
        },
    )
    assert resp.status_code == 200
    assert resp.text == "# Summary"
