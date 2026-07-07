"""Smoke tests for FastAPI routers — verify all endpoints respond."""

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
