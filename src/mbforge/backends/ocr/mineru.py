"""MinerU cloud OCR backend.

MinerU is an async service:
  POST /api/v4/extract/task       submit a job (returns task_id)
  GET  /api/v4/extract/task/{id}  poll until completed

We submit the page image as a base64 data URL (`data:image/png;base64,…`)
and wait for the result. Polling interval 4s, timeout 120s.
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

import httpx

from .base import OCRBackend, OCRResult

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://mineru.net"
SUBMIT_PATH = "/api/v4/extract/task"
POLL_PATH_TMPL = "/api/v4/extract/task/{task_id}"

POLL_INTERVAL_S = 4
TIMEOUT_S = 120


class MinerUBackend(OCRBackend):
    name = "mineru"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        cfg = config or {}
        self.api_key: str = (cfg.get("api_key") or "").strip()
        base_url = (cfg.get("base_url") or "").strip() or DEFAULT_BASE_URL
        self.base_url = base_url.rstrip("/")
        self.model_version: str = (cfg.get("model_version") or "vlm").strip()

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def extract_text(self, image: bytes) -> OCRResult:
        if not self.is_configured():
            return OCRResult(text="", error="MinerU api_key not set")
        data_url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
        try:
            task_id = self._submit(data_url)
            text = self._poll(task_id)
            return OCRResult(text=text)
        except Exception as exc:  # noqa: BLE001 — surface as chain-eligible failure
            logger.warning("MinerU OCR failed: %s", exc)
            return OCRResult(text="", error=str(exc))

    def _submit(self, data_url: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {"url": data_url, "model_version": self.model_version}
        with httpx.Client(timeout=30) as client:
            r = client.post(
                f"{self.base_url}{SUBMIT_PATH}",
                headers=headers,
                json=body,
            )
            r.raise_for_status()
            payload = r.json()
        if payload.get("code") not in (0, None):
            raise RuntimeError(
                f"MinerU submit rejected: {payload.get('msg') or payload}"
            )
        data = payload.get("data") or {}
        task_id = data.get("task_id")
        if not task_id:
            raise RuntimeError(f"MinerU submit returned no task_id: {payload}")
        return task_id

    def _poll(self, task_id: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        deadline = time.monotonic() + TIMEOUT_S
        with httpx.Client(timeout=30) as client:
            while True:
                if time.monotonic() > deadline:
                    raise TimeoutError(f"MinerU task {task_id} did not finish in {TIMEOUT_S}s")
                r = client.get(
                    f"{self.base_url}{POLL_PATH_TMPL.format(task_id=task_id)}",
                    headers=headers,
                )
                r.raise_for_status()
                payload = r.json()
                data = payload.get("data") or {}
                state = (data.get("state") or "").lower()
                if state in ("done", "success", "completed"):
                    return self._extract_text_from_result(data)
                if state in ("failed", "error", "cancelled"):
                    raise RuntimeError(f"MinerU task {task_id} ended in state={state}")
                time.sleep(POLL_INTERVAL_S)

    @staticmethod
    def _extract_text_from_result(data: dict[str, Any]) -> str:
        """Pull plain text out of MinerU's nested result structure.

        MinerU returns markdown by default. We accept either:
        - `data["full_md_link"]` (URL to fetch markdown)
        - `data["md_content"]` (inlined markdown)
        - `data["content"]` (raw text)
        Markdown is fine for our downstream pipeline (chunking works on
        prose). Images and tables are kept as text/markdown markers.
        """
        for key in ("full_md_link", "md_content", "content"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""
