"""PaddleOCR cloud backend (v2 async API: submit → poll → result).

Posts a page image to the configured job endpoint, polls for completion,
and returns extracted text. The v2 API uses an async job pattern:
  POST {host}          (multipart file upload) → {"job_id": "..."}
  GET  {host}/{job_id} (poll until done)       → {"status": "success", "result": [...]}

Reference: PaddleOCR v2 API (official SDK at paddleocr._api_client).
"""

from __future__ import annotations

import json
import logging
import time

import httpx

from .base import OCRBackend, OCRResult

logger = logging.getLogger(__name__)

DEFAULT_HOST = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
POLL_INTERVAL = 1.0  # seconds between status checks
POLL_TIMEOUT = 60.0  # max seconds to wait for a job
MAX_RESPONSE_TEXT = 200  # chars of response body to log for debugging


class PaddleOCRBackend(OCRBackend):
    name = "paddleocr"

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}
        self.api_key: str = (cfg.get("api_key") or "").strip()
        self.host: str = (cfg.get("host") or "").strip() or DEFAULT_HOST
        self.model: str = (cfg.get("model") or "PaddleOCR-VL-1.6").strip()

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def extract_text(self, image: bytes) -> OCRResult:
        if not self.is_configured():
            return OCRResult(text="", error="PaddleOCR api_key not set")

        base = self.host.rstrip("/")

        try:
            with httpx.Client(timeout=POLL_TIMEOUT + 10) as client:
                # 1) Submit — upload image, get job_id
                job_id = self._submit(client, base, image)
                if not job_id:
                    return OCRResult(text="", error="PaddleOCR: no job_id returned")

                # 2) Poll — wait for completion
                result_data = self._poll(client, base, job_id)
                if result_data is None:
                    return OCRResult(
                        text="",
                        error=f"PaddleOCR: job {job_id} did not complete within {POLL_TIMEOUT}s",
                    )

                # 3) Parse result
                text = self._extract_text(result_data)
                return OCRResult(text=text)

        except Exception as exc:  # noqa: BLE001
            logger.warning("PaddleOCR failed: %s", exc)
            return OCRResult(text="", error=str(exc))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _submit(self, client: httpx.Client, base: str, image: bytes) -> str | None:
        """Upload image and return job_id."""
        r = client.post(
            base,
            headers={"Authorization": f"Bearer {self.api_key}"},
            files={"file": ("page.png", image, "image/png")},
        )
        r.raise_for_status()
        payload = r.json()
        job_id = payload.get("job_id") or payload.get("id")
        if job_id:
            logger.debug("PaddleOCR job submitted: %s", job_id)
        else:
            logger.warning(
                "PaddleOCR submit response has no job_id: %s",
                json.dumps(payload)[:MAX_RESPONSE_TEXT],
            )
        return job_id

    def _poll(self, client: httpx.Client, base: str, job_id: str) -> dict | None:
        """Poll job status until success/failure or timeout.

        Returns the result dict on success, None on timeout/failure.
        """
        status_url = f"{base}/{job_id}"
        deadline = time.monotonic() + POLL_TIMEOUT

        while time.monotonic() < deadline:
            r = client.get(
                status_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            r.raise_for_status()
            payload = r.json()
            status = (payload.get("status") or "").lower()

            if status == "success":
                # Result may be in "result" key or top-level
                result = payload.get("result") or payload
                if isinstance(result, dict):
                    return result
                return payload

            if status in ("failed", "error"):
                err = payload.get("error") or payload.get("message") or "unknown"
                logger.warning("PaddleOCR job %s failed: %s", job_id, err)
                return None

            time.sleep(POLL_INTERVAL)

        logger.warning("PaddleOCR job %s timed out after %.0fs", job_id, POLL_TIMEOUT)
        return None

    @staticmethod
    def _extract_text(payload: dict) -> str:
        """Tolerate multiple response shapes across PaddleOCR versions."""
        # Shape A: {"words_result": [{"words": "...", "confidence": ...}]}
        words = payload.get("words_result")
        if isinstance(words, list):
            return "\n".join(
                item.get("words", "")
                for item in words
                if isinstance(item, dict)
            )
        # Shape B: {"result": [{"text": "...", "score": ...}]}
        result = payload.get("result")
        if isinstance(result, list):
            return "\n".join(
                item.get("text", "")
                for item in result
                if isinstance(item, dict)
            )
        # Shape C: {"text": "..."}
        if isinstance(payload.get("text"), str):
            return payload["text"]
        return ""
