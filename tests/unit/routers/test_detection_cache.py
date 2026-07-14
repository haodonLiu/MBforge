"""detection-cache router: real read/clear/stats against molecule_detections."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mbforge.core.database import DatabaseManager


def _seed_detection(library_root: Path, doc_id: str = "doc1", page: int = 1) -> None:
    db = DatabaseManager.get(library_root)
    db.initialize()
    with db.mol_conn() as conn:
        conn.execute(
            """
            INSERT INTO molecule_detections
                (mol_id, doc_id, page, bbox_x0, bbox_y0, bbox_x1, bbox_y1,
                 crop_relpath, conf_moldet, conf_molscribe, vlm_verified_esmiles)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            # mol_id NULL avoids FK to molecules for cache-only rows
            (None, doc_id, page, 0.1, 0.2, 0.3, 0.4, "crop.png", 0.9, 0.8, "CCO"),
        )


def test_detection_cache_get_stats_clear(app_client: TestClient, tmp_library: Path) -> None:
    _seed_detection(tmp_library)

    stats = app_client.post(
        "/api/v1/detection-cache/stats",
        json={"library_root": str(tmp_library)},
    )
    assert stats.status_code == 200
    body = stats.json()
    assert body["cached_page_count"] >= 1
    assert body["cached_doc_count"] >= 1

    got = app_client.post(
        "/api/v1/detection-cache/get",
        json={"library_root": str(tmp_library), "doc_id": "doc1", "page": 1},
    )
    assert got.status_code == 200
    data = got.json()
    assert data["count"] == 1
    assert data["source"] == "cache"
    assert len(data["results"]) == 1
    assert data["results"][0]["esmiles"] == "CCO"
    # back-compat alias
    assert len(data["detections"]) == 1

    cleared = app_client.post(
        "/api/v1/detection-cache/clear-doc",
        json={"library_root": str(tmp_library), "doc_id": "doc1"},
    )
    assert cleared.status_code == 200
    assert cleared.json()["success"] is True
    assert cleared.json()["cleared"] >= 1

    after = app_client.post(
        "/api/v1/detection-cache/get",
        json={"library_root": str(tmp_library), "doc_id": "doc1", "page": 1},
    )
    assert after.json()["count"] == 0
    assert after.json()["source"] == "cache_miss"
