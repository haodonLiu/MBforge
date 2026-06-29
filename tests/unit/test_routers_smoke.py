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
    def test_project_open(self, tmp_path):
        c = _client()
        r = c.post("/api/v1/project/open", json={"path": str(tmp_path)})
        assert r.status_code == 200
        assert "success" in r.json()

    def test_project_scan(self, tmp_path):
        c = _client()
        c.post("/api/v1/project/open", json={"path": str(tmp_path)})
        r = c.post("/api/v1/project/scan", json={"root": str(tmp_path)})
        assert r.status_code == 200

    def test_project_file_tree(self, tmp_path):
        c = _client()
        c.post("/api/v1/project/open", json={"path": str(tmp_path)})
        r = c.post("/api/v1/project/file-tree", json={"root": str(tmp_path)})
        assert r.status_code == 200


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
        c.post("/api/v1/project/open", json={"path": str(tmp_path)})
        r = c.post("/api/v1/pipeline/queue/stats", json={"root": str(tmp_path)})
        assert r.status_code == 200


class TestKBEndpoints:
    def test_kb_search_empty(self, tmp_path):
        c = _client()
        c.post("/api/v1/project/open", json={"path": str(tmp_path)})
        r = c.post("/api/v1/kb/search", json={"root": str(tmp_path), "query": "test"})
        assert r.status_code == 200


class TestMoleculeEndpoints:
    def test_mol_list_empty(self, tmp_path):
        c = _client()
        c.post("/api/v1/project/open", json={"path": str(tmp_path)})
        r = c.post("/api/v1/molecule/list", json={"root": str(tmp_path)})
        assert r.status_code == 200

    def test_mol_stats(self, tmp_path):
        c = _client()
        c.post("/api/v1/project/open", json={"path": str(tmp_path)})
        r = c.post("/api/v1/molecule/stats", json={"root": str(tmp_path)})
        assert r.status_code == 200


class TestChemEndpoints:
    def test_validate_smiles(self):
        c = _client()
        r = c.post("/api/v1/chem/validate-smiles", json={"smiles": "CCO"})
        assert r.status_code == 200


class TestNotesEndpoints:
    def test_notes_get(self, tmp_path):
        c = _client()
        c.post("/api/v1/project/open", json={"path": str(tmp_path)})
        r = c.post("/api/v1/notes/get", json={
            "root": str(tmp_path),
            "doc_id": "test_doc",
        })
        assert r.status_code == 200


class TestDetectionCacheEndpoints:
    def test_detection_cache_get(self, tmp_path):
        c = _client()
        c.post("/api/v1/project/open", json={"path": str(tmp_path)})
        r = c.post("/api/v1/detection-cache/get", json={
            "root": str(tmp_path),
            "doc_id": "test_doc",
            "page": 1,
        })
        assert r.status_code == 200
