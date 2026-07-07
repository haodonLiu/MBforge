"""HTTP client for MBForge FastAPI backend."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .models import (
    IngestTask,
    MoleculeListResponse,
    MoleculeRecord,
    NoteEntry,
    PipelineStats,
    SearchResult,
)

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """API request error."""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    """Synchronous HTTP client for MBForge backend.

    Features:
    - Connection pooling via httpx.Client
    - Automatic retry on transient errors
    - Structured error handling
    """

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
                keepalive_expiry=30,
            ),
        )

    def close(self) -> None:
        """Close the HTTP client and release connections."""
        try:
            self.client.close()
        except Exception as e:
            logger.warning("Error closing API client: %s", e)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ── Helpers ─────────────────────────────────────────────

    def _post(self, path: str, body: dict | None = None) -> dict:
        """POST request with error handling."""
        try:
            resp = self.client.post(path, json=body or {})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("HTTP %d: %s", e.response.status_code, path)
            raise ApiError(f"HTTP {e.response.status_code}", e.response.status_code) from e
        except httpx.RequestError as e:
            logger.error("Request failed: %s - %s", path, e)
            raise ApiError(f"Request failed: {e}") from e

    def _get(self, path: str, params: dict | None = None) -> dict:
        """GET request with error handling."""
        try:
            resp = self.client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("HTTP %d: %s", e.response.status_code, path)
            raise ApiError(f"HTTP {e.response.status_code}", e.response.status_code) from e
        except httpx.RequestError as e:
            logger.error("Request failed: %s - %s", path, e)
            raise ApiError(f"Request failed: {e}") from e

    # ── Health ──────────────────────────────────────────────

    def health_check(self) -> bool:
        try:
            resp = self.client.get("/api/v1/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    # ── Project ─────────────────────────────────────────────
    # The legacy `/api/v1/project/*` router chain was retired in commit
    # 7c9fc9e (backend) and 8b1b8d6 (frontend). For GUI-side hooks that
    # need them, callers should migrate to `/api/v1/library/*` equivalents.

    def open_project(self, root: str, name: str = "") -> dict:
        """Compatibility: configure library_root. Returns a dict the legacy
        callers can still treat as a ProjectResponse-shaped value."""
        data = self._post("/api/v1/library/configure", {"root": root})
        if not data.get("success"):
            return {"success": False, "root": "", "name": ""}
        derived = root.rstrip("/\\").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return {"success": True, "root": root, "name": data.get("root", derived) or derived}

    def list_documents(self, _root: str) -> list[dict]:
        """Compat stub — the legacy project router is gone. Returns an
        empty document list so the workspace view mounts cleanly. Use
        ``library.list_documents`` once the GUI exposes a library view.
        """
        return []

    def scan_files(self, _root: str, _recursive: bool = False) -> list[dict]:
        """Compat stub — legacy filesystem-walk endpoint is gone. Returns
        empty scan; enqueue flow uses pipeline router instead."""
        return []


# Backwards-compat aliases removed with the legacy router — keep names out
# of the public surface unless a caller truly needs them.

    # ── Molecules ───────────────────────────────────────────

    def list_molecules(
        self, root: str, page: int = 1, page_size: int = 50, status: str = ""
    ) -> MoleculeListResponse:
        body: dict[str, Any] = {"library_root": root, "page": page, "page_size": page_size}
        if status:
            body["status"] = status
        data = self._post("/api/v1/molecule/list", body)
        items = [MoleculeRecord(**m) for m in data.get("items", [])]
        return MoleculeListResponse(
            success=data.get("success", True), items=items, total=data.get("total", 0)
        )

    def search_molecules(self, root: str, query: str, top_k: int = 20) -> list[MoleculeRecord]:
        data = self._post(
            "/api/v1/molecule/search",
            {"library_root": root, "query": query, "top_k": top_k},
        )
        results = data.get("results", [])
        return [MoleculeRecord(**m) for m in results]

    def create_molecule(
        self, root: str, smiles: str, name: str = "", esmiles: str = ""
    ) -> str:
        data = self._post(
            "/api/v1/molecule/create",
            {"library_root": root, "smiles": smiles, "name": name, "esmiles": esmiles},
        )
        return data.get("mol_id", "")

    def update_molecule(self, root: str, mol_id: str, **fields) -> bool:
        body: dict[str, Any] = {"library_root": root, **fields}
        resp = self.client.put(f"/api/v1/molecule/{mol_id}", json=body)
        resp.raise_for_status()
        return resp.json().get("success", False)

    def delete_molecule(self, root: str, mol_id: str) -> bool:
        resp = self.client.delete(
            f"/api/v1/molecule/{mol_id}",
            json={"library_root": root},
        )
        resp.raise_for_status()
        return resp.json().get("success", False)

    def molecule_stats(self, root: str) -> dict:
        return self._post("/api/v1/molecule/stats", {"library_root": root})

    # ── Knowledge Base ──────────────────────────────────────

    def kb_search(self, query: str, root: str, top_k: int = 10) -> list[SearchResult]:
        data = self._post(
            "/api/v1/kb/search",
            {"query": query, "library_root": root, "top_k": top_k},
        )
        results = data.get("results", [])
        return [SearchResult(**r) for r in results]

    # ── Notes ───────────────────────────────────────────────

    def list_notes(self, root: str) -> list[NoteEntry]:
        data = self._post("/api/v1/notes/list", {"library_root": root})
        notes = data.get("notes", [])
        return [NoteEntry(**n) for n in notes]

    def get_note(self, root: str, note_id: str) -> str:
        data = self._post("/api/v1/notes/get", {"library_root": root, "id": note_id})
        return data.get("notes", "")

    def save_note(self, root: str, note: NoteEntry) -> bool:
        body = {
            "library_root": root,
            "note": {
                "id": note.id,
                "title": note.title,
                "content": note.content,
                "tags": note.tags,
                "links": note.links,
                "createdAt": note.created_at,
                "updatedAt": note.updated_at,
            },
        }
        data = self._post("/api/v1/notes/save", body)
        return data.get("success", False)

    def delete_note(self, root: str, note_id: str) -> bool:
        data = self._post("/api/v1/notes/delete", {"library_root": root, "id": note_id})
        return data.get("success", False)

    def get_backlinks(self, root: str, target_id: str) -> list[NoteEntry]:
        data = self._post(
            "/api/v1/notes/backlinks", {"library_root": root, "target_id": target_id}
        )
        links = data.get("backlinks", [])
        return [NoteEntry(**n) for n in links]

    # ── Settings ────────────────────────────────────────────

    def get_settings(self) -> dict:
        data = self._get("/api/v1/settings")
        return data.get("settings", {})

    def save_settings(self, settings: dict) -> bool:
        data = self._post("/api/v1/settings", settings)
        return data.get("success", False)

    # ── Pipeline ────────────────────────────────────────────

    def enqueue_documents(self, root: str) -> int:
        data = self._post(
            "/api/v1/pipeline/enqueue",
            {"library_root": root, "action": "enqueue_unresolved"},
        )
        return data.get("enqueued", 0)

    def get_queue(self, root: str) -> list[IngestTask]:
        data = self._post("/api/v1/pipeline/queue", {"library_root": root})
        tasks = data.get("tasks", [])
        return [IngestTask(**t) for t in tasks]

    def get_queue_stats(self, root: str) -> PipelineStats:
        data = self._post("/api/v1/pipeline/queue/stats", {"library_root": root})
        return PipelineStats(
            total=data.get("total", 0),
            pending=data.get("pending", 0),
            processing=data.get("processing", 0),
            done=data.get("done", 0),
            failed=data.get("failed", 0),
        )

    def cancel_task(self, root: str, task_id: str) -> bool:
        data = self._post(f"/api/v1/pipeline/queue/{task_id}/cancel", {"library_root": root})
        return data.get("success", False)

    def retry_task(self, root: str, task_id: str) -> bool:
        data = self._post(f"/api/v1/pipeline/queue/{task_id}/retry", {"library_root": root})
        return data.get("success", False)

    def delete_task(self, root: str, task_id: str) -> bool:
        data = self._post(f"/api/v1/pipeline/queue/{task_id}/delete", {"library_root": root})
        return data.get("success", False)

    def get_worker_status(self) -> dict:
        return self._get("/api/v1/pipeline/worker/status")

    # ── Agent ───────────────────────────────────────────────

    def agent_init(self) -> bool:
        data = self._post("/api/v1/agent/init")
        return data.get("agent_ready", False)

    def agent_create_session(self, root: str) -> str:
        data = self._post("/api/v1/agent/session", {"library_root": root})
        return data.get("session_id", "")

    def agent_chat(self, session_id: str, message: str) -> str:
        data = self._post(
            f"/api/v1/agent/session/{session_id}/chat",
            {"user_input": message},
        )
        return data.get("reply", "")

    def agent_get_history(self, session_id: str) -> list[dict]:
        data = self._get(f"/api/v1/agent/session/{session_id}/history")
        return data.get("messages", [])

    def agent_destroy_session(self, session_id: str) -> bool:
        resp = self.client.delete(f"/api/v1/agent/session/{session_id}")
        resp.raise_for_status()
        return resp.json().get("success", False)

    # ── SAR ─────────────────────────────────────────────────

    def sar_find_scaffold(self, smiles: str) -> dict:
        return self._post("/api/v1/sar/find-scaffold", {"smiles": smiles})

    def sar_decompose(self, smiles: str) -> dict:
        return self._post("/api/v1/sar/decompose", {"smiles": smiles})

    def sar_build_matrix(self, core_smiles: str) -> dict:
        return self._post("/api/v1/sar/build-matrix", {"coreSmiles": core_smiles})

    def sar_heatmap(self, data: dict) -> list:
        return self._post("/api/v1/sar/heatmap", data)
