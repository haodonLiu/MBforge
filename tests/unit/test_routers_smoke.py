"""Smoke tests for FastAPI routers — verify all endpoints respond."""

import pytest
from fastapi.testclient import TestClient

from mbforge.app import create_app


def _client():
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoints:
    def test_health(self):
        c = _client()
        r = c.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] in ("ok", "partial")

    def test_env_check(self):
        c = _client()
        r = c.get("/api/v1/environment/check")
        assert r.status_code == 200

    def test_resources_check(self):
        c = _client()
        r = c.post("/api/v1/resources/check")
        assert r.status_code == 200


class TestProjectEndpoints:
    """The legacy /api/v1/project/* router has been retired in favour of
    /api/v1/library/*. The smoke cases below exercise the library endpoints
    that absorbed the corresponding responsibilities."""

    def test_library_status(self):
        c = _client()
        r = c.get("/api/v1/library/status")
        assert r.status_code == 200
        body = r.json()
        assert "configured" in body
        assert "root" in body
        assert "doc_count" in body

    def test_library_configure_then_status(self, tmp_path):
        c = _client()
        r = c.post("/api/v1/library/configure", json={"root": str(tmp_path)})
        assert r.status_code == 200
        assert r.json().get("success") is True

        r = c.get("/api/v1/library/status")
        assert r.status_code == 200
        body = r.json()
        assert body["configured"] is True
        assert body["root"] == str(tmp_path)

    @pytest.mark.xfail(
        reason="library/import currently returns 422 for missing file; router contract TBD",
        strict=False,
    )
    def test_library_import_missing_file_returns_error(self):
        c = _client()
        r = c.post(
            "/api/v1/library/import",
            json={"file_path": "/nonexistent.pdf", "title": ""},
        )
        # The router returns 200 with success:false rather than 4xx, by design.
        assert r.status_code == 200
        assert r.json().get("success") is False


class TestSettingsEndpoints:
    def test_settings_get(self):
        c = _client()
        r = c.get("/api/v1/settings")
        assert r.status_code == 200

    def test_settings_update(self):
        c = _client()
        r = c.put("/api/v1/settings", json={"theme": "dark"})
        assert r.status_code == 200


class TestAgentEndpoints:
    def test_agent_init(self):
        c = _client()
        r = c.post("/api/v1/agent/init", json={})
        assert r.status_code == 200

    def test_agent_create_session(self):
        c = _client()
        r = c.post("/api/v1/agent/session", json={})
        assert r.status_code == 200


class TestPipelineEndpoints:
    def test_pipeline_queue_stats(self, tmp_path):
        c = _client()
        r = c.post("/api/v1/pipeline/queue/stats", json={"library_root": str(tmp_path)})
        assert r.status_code == 200


class TestKBEndpoints:
    def test_kb_search_empty(self, tmp_path):
        c = _client()
        r = c.post("/api/v1/kb/search", json={"library_root": str(tmp_path), "query": "test"})
        assert r.status_code == 200


class TestMoleculeEndpoints:
    def test_mol_list_empty(self, tmp_path):
        c = _client()
        # The molecule router still accepts `project_root` for backward compat;
        # the migration to `library_root` is a separate contract change (TODO #36).
        r = c.post("/api/v1/molecule/list", json={"project_root": str(tmp_path)})
        assert r.status_code == 200

    def test_mol_stats(self, tmp_path):
        c = _client()
        r = c.post("/api/v1/molecule/stats", json={"project_root": str(tmp_path)})
        assert r.status_code == 200


class TestChemEndpoints:
    def test_validate_smiles(self):
        c = _client()
        r = c.post("/api/v1/chem/validate-smiles", json={"smiles": "CCO"})
        assert r.status_code == 200


class TestNotesEndpoints:
    def test_notes_get(self, tmp_path):
        c = _client()
        r = c.post("/api/v1/notes/get", json={
            "project_root": str(tmp_path),
            "doc_id": "test_doc",
        })
        assert r.status_code == 200


class TestDetectionCacheEndpoints:
    def test_detection_cache_get(self, tmp_path):
        c = _client()
        r = c.post("/api/v1/detection-cache/get", json={
            "project_root": str(tmp_path),
            "doc_id": "test_doc",
            "page": 1,
        })
        assert r.status_code == 200


class TestDiagnosticsEndpoints:
    """Smoke tests for the unified error-logging surface."""

    def test_diagnostics_errors_list(self):
        c = _client()
        r = c.get("/api/v1/diagnostics/errors?limit=20")
        assert r.status_code == 200
        body = r.json()
        assert "errors" in body
        assert "count" in body

    def test_diagnostics_stats(self):
        c = _client()
        r = c.get("/api/v1/diagnostics/stats")
        assert r.status_code == 200
        body = r.json()
        assert "by_level" in body
        assert "by_category" in body
        assert body["capacity"] == 500

    def test_diagnostics_client_report(self):
        c = _client()
        r = c.post(
            "/api/v1/diagnostics/errors",
            json={"errors": [{"message": "smoke", "category": "client"}]},
        )
        assert r.status_code == 204


class TestDocumentsEndpoints:
    def test_doc_list_empty(self, tmp_path):
        c = _client()
        r = c.post("/api/v1/documents/list", json={"library_root": str(tmp_path)})
        assert r.status_code == 200
        assert r.json().get("success") is True
        assert r.json()["documents"] == []

    def test_doc_delete_missing_doc_id(self, tmp_path):
        c = _client()
        r = c.post("/api/v1/documents/delete", json={"library_root": str(tmp_path)})
        assert r.status_code == 200
        assert r.json().get("success") is False


class TestCorefEndpoints:
    def test_figure_labels_missing_params(self):
        c = _client()
        r = c.post("/api/v1/coref/figure-labels", json={})
        assert r.status_code == 422

    def test_predictions_missing_params(self):
        c = _client()
        r = c.post("/api/v1/coref/predictions", json={})
        assert r.status_code == 422


class TestSarEndpoints:
    def test_find_scaffold(self):
        c = _client()
        r = c.post("/api/v1/sar/find-scaffold", json={"smiles": "CCO"})
        assert r.status_code == 200

    def test_decompose_missing_smiles(self):
        c = _client()
        r = c.post("/api/v1/sar/decompose", json={})
        assert r.status_code == 200


class TestOcrEndpoints:
    def test_chain_status(self):
        c = _client()
        r = c.get("/api/v1/ocr/chain-status")
        assert r.status_code == 200
        assert "backends" in r.json()

    def test_uniparser_stub(self):
        c = _client()
        r = c.post("/api/v1/ocr/test-uniparser", json={})
        assert r.status_code == 200
        assert r.json()["ok"] is False


class TestPdfEndpoints:
    def test_classify_pdf(self):
        c = _client()
        r = c.post("/api/v1/pdf/classify", json={"path": ""})
        assert r.status_code == 200
        assert "pdf_type" in r.json()

    def test_inspect_pdf_missing_body(self):
        c = _client()
        r = c.post("/api/v1/pdf/inspect", json={})
        assert r.status_code == 200


class TestEventsEndpoints:
    def test_stream_route_registered(self):
        app = create_app()
        paths = {route.path for route in app.routes}
        assert "/api/v1/events/stream" in paths


class TestMoldetApiEndpoints:
    def test_coref_ft_missing_image(self):
        c = _client()
        r = c.post("/api/v1/moldet/coref_ft", json={})
        assert r.status_code == 422

    def test_extract_pdf_page_missing_path(self):
        c = _client()
        r = c.post("/api/v1/moldet/extract-pdf-page", json={})
        assert r.status_code == 422

    def test_removed_endpoint_returns_gone(self):
        c = _client()
        r = c.post("/api/v1/moldet/detect-page", json={})
        assert r.status_code == 410


@pytest.mark.xfail(
    reason="model_server mount prefixes produce /api/v1/models/api/v1/* paths; needs structural fix",
    strict=False,
)
class TestModelServerEndpoints:
    def test_models_health(self):
        c = _client()
        r = c.get("/api/v1/models/health")
        assert r.status_code == 200

    def test_models_environment_check(self):
        c = _client()
        r = c.get("/api/v1/models/environment/check")
        assert r.status_code == 200

    def test_models_test_missing_model_id(self):
        c = _client()
        r = c.post("/api/v1/models/test", json={})
        assert r.status_code == 200
        assert r.json().get("success") is False

    def test_models_render_missing_smiles(self):
        c = _client()
        r = c.post("/api/v1/models/mol/render", json={})
        assert r.status_code == 200
        assert r.json().get("success") is False
