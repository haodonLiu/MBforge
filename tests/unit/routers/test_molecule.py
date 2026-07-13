from __future__ import annotations

from fastapi.testclient import TestClient


def _assert_error(response, expected_status: int, expected_error_code: str) -> dict:
    assert response.status_code == expected_status, response.text
    data = response.json()
    assert data["success"] is False
    assert data["error_code"] == expected_error_code
    return data


def test_molecule_create_and_get(app_client: TestClient, tmp_path) -> None:
    root = str(tmp_path)
    resp = app_client.post(
        "/api/v1/molecule/create",
        json={"library_root": root, "smiles": "CCO", "name": "Ethanol"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    mol_id = data["mol_id"]

    resp = app_client.post(
        "/api/v1/molecule/get",
        json={"library_root": root, "mol_id": mol_id},
    )
    assert resp.status_code == 200
    assert resp.json()["molecule"]["smiles"] == "CCO"


def test_molecule_list_and_stats(app_client: TestClient, tmp_path) -> None:
    root = str(tmp_path)
    app_client.post(
        "/api/v1/molecule/create",
        json={"library_root": root, "smiles": "CCO", "source_type": "manual"},
    )
    resp = app_client.post(
        "/api/v1/molecule/list",
        json={"library_root": root, "page": 1, "page_size": 10},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    resp = app_client.post("/api/v1/molecule/stats", json={"library_root": root})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_molecule_update_and_delete(app_client: TestClient, tmp_path) -> None:
    root = str(tmp_path)
    resp = app_client.post(
        "/api/v1/molecule/create",
        json={"library_root": root, "smiles": "CCO"},
    )
    mol_id = resp.json()["mol_id"]
    resp = app_client.put(
        f"/api/v1/molecule/{mol_id}",
        json={"library_root": root, "name": "Updated"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    resp = app_client.post(
        "/api/v1/molecule/get",
        json={"library_root": root, "mol_id": mol_id},
    )
    assert resp.json()["molecule"]["name"] == "Updated"


def test_molecule_get_unknown_returns_404(app_client: TestClient, tmp_path) -> None:
    root = str(tmp_path)
    _assert_error(
        app_client.post(
            "/api/v1/molecule/get",
            json={"library_root": root, "mol_id": "no-such-mol"},
        ),
        404,
        "not_found",
    )


def test_molecule_evidence_unknown_returns_404(app_client: TestClient, tmp_path) -> None:
    root = str(tmp_path)
    _assert_error(
        app_client.post(
            "/api/v1/molecule/evidence",
            json={"library_root": root, "canonical_smiles": "no-such-mol"},
        ),
        404,
        "not_found",
    )


def test_molecule_update_no_fields_returns_422(app_client: TestClient, tmp_path) -> None:
    root = str(tmp_path)
    resp = app_client.post(
        "/api/v1/molecule/create",
        json={"library_root": root, "smiles": "CCO"},
    )
    mol_id = resp.json()["mol_id"]
    _assert_error(
        app_client.put(f"/api/v1/molecule/{mol_id}", json={"library_root": root}),
        422,
        "validation_error",
    )
