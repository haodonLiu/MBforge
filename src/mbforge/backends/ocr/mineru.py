"""MinerU cloud OCR backend via batch upload API.

API flow (per the official docs at https://mineru.net/apiManage/docs):

  POST /api/v4/file-urls/batch    request OSS upload URLs (batch_id + file_urls)
  PUT  {file_url}                 upload file binary to OSS (auto-starts processing)
  GET  /api/v4/extract-results/batch/{batch_id}   poll until done
  GET  {full_zip_url}             download result ZIP (contains markdown)

Notes:
  - MinerU does NOT support data:image/png;base64 URLs in /api/v4/extract/task.
  - The batch API has a limit of 50 files per request.
  - OSS upload URLs expire in 24 hours.
"""

from __future__ import annotations

import io
import logging
import time
import zipfile
from typing import Any

import httpx

from .base import OCRBackend, OCRResult

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://mineru.net"
BATCH_URL_PATH = "/api/v4/file-urls/batch"
BATCH_RESULT_PATH_TMPL = "/api/v4/extract-results/batch/{batch_id}"

POLL_INTERVAL_S = 2
TIMEOUT_S = 120


class MinerUBackend(OCRBackend):
    """MinerU OCR backend using batch upload + poll."""

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
        """OCR a single page image via MinerU batch upload API."""
        if not self.is_configured():
            return OCRResult(text="", error="MinerU api_key not set")

        file_name = "page.png"

        try:
            # Step 1: Request OSS upload URL
            batch_id, upload_urls = self._request_batch_urls([file_name])
            if not upload_urls:
                return OCRResult(text="", error="MinerU returned no upload URLs")
            upload_url = upload_urls[0]

            # Step 2: Upload image to OSS
            self._upload_to_oss(upload_url, image)

            # Step 3: Poll batch results
            text = self._poll_batch(batch_id, file_name)
            return OCRResult(text=text)

        except Exception as exc:  # noqa: BLE001 — surface as chain-eligible failure
            logger.warning("MinerU OCR failed: %s", exc)
            return OCRResult(text="", error=str(exc))

    def extract_text_batch(
        self, images: list[bytes]
    ) -> list[OCRResult]:
        """OCR multiple page images in a single MinerU batch request.

        Args:
            images: list of page image bytes (max 50 per MinerU limit).

        Returns:
            list of OCRResult, one per input image, in order.
        """
        if not self.is_configured():
            return [OCRResult(text="", error="MinerU api_key not set")] * len(images)

        if not images:
            return []

        file_names = [f"page_{i}.png" for i in range(len(images))]

        try:
            # Step 1: Request OSS upload URLs for all pages
            batch_id, upload_urls = self._request_batch_urls(file_names)
            if len(upload_urls) != len(images):
                return [OCRResult(text="", error="MinerU returned wrong URL count")] * len(images)

            # Step 2: Upload all images to OSS in parallel
            for url, img_bytes in zip(upload_urls, images, strict=True):
                self._upload_to_oss(url, img_bytes)

            # Step 3: Poll batch results, extract text for each file
            entries = self._poll_batch_all(batch_id, file_names)

            results: list[OCRResult] = []
            for fname in file_names:
                entry = entries.get(fname)
                if entry is None:
                    results.append(OCRResult(text="", error="missing result"))
                else:
                    text = self._extract_text_from_entry(entry)
                    results.append(OCRResult(text=text))
            return results

        except Exception as exc:  # noqa: BLE001
            logger.warning("MinerU batch OCR failed: %s", exc)
            return [OCRResult(text="", error=str(exc))] * len(images)

    def _request_batch_urls(
        self, file_names: list[str]
    ) -> tuple[str, list[str]]:
        """Request batch upload URLs from MinerU.

        Returns (batch_id, list_of_oss_upload_urls).
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "files": [{"name": fn} for fn in file_names],
            "model_version": self.model_version,
        }
        with httpx.Client(timeout=30) as client:
            r = client.post(
                f"{self.base_url}{BATCH_URL_PATH}",
                headers=headers,
                json=body,
            )
            r.raise_for_status()
            payload = r.json()

        if payload.get("code") not in (0, None):
            raise RuntimeError(
                f"MinerU batch-url request rejected: {payload.get('msg') or payload}"
            )

        data = payload.get("data") or {}
        batch_id = data.get("batch_id")
        if not batch_id:
            raise RuntimeError(f"MinerU batch-url returned no batch_id: {payload}")

        file_urls: list[str] = data.get("file_urls") or []
        if len(file_urls) != len(file_names):
            raise RuntimeError(
                f"MinerU returned {len(file_urls)} URLs for {len(file_names)} files"
            )

        return batch_id, file_urls

    @staticmethod
    def _upload_to_oss(upload_url: str, data: bytes) -> None:
        """PUT file binary to OSS signed URL.

        MinerU docs say: no Content-Type header needed.
        """
        with httpx.Client(timeout=60) as client:
            r = client.put(upload_url, content=data)
            r.raise_for_status()

    def _poll_batch(self, batch_id: str, target_file: str) -> str:
        """Poll batch results until done, return text for ``target_file``."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        deadline = time.monotonic() + TIMEOUT_S

        with httpx.Client(timeout=30) as client:
            while True:
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"MinerU batch {batch_id} did not finish in {TIMEOUT_S}s"
                    )

                r = client.get(
                    f"{self.base_url}{BATCH_RESULT_PATH_TMPL.format(batch_id=batch_id)}",
                    headers=headers,
                )
                r.raise_for_status()
                payload = r.json()

                data = payload.get("data") or {}
                results = data.get("extract_result") or []
                if not results:
                    time.sleep(POLL_INTERVAL_S)
                    continue

                # Find our target file's result
                match = None
                for entry in results:
                    if entry.get("file_name") == target_file:
                        match = entry
                        break
                if not match:
                    # File not yet in results — still processing
                    time.sleep(POLL_INTERVAL_S)
                    continue

                state = (match.get("state") or "").lower()
                err_msg = match.get("err_msg") or ""

                if state in ("done", "success", "completed"):
                    return self._extract_text_from_entry(match)
                if state in ("failed", "error", "cancelled"):
                    raise RuntimeError(
                        f"MinerU batch {batch_id} file {target_file} ended "
                        f"in state={state}: {err_msg}"
                    )

                time.sleep(POLL_INTERVAL_S)

    def _poll_batch_all(
        self, batch_id: str, file_names: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Poll batch results until all files are done, return {file_name: entry}."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        deadline = time.monotonic() + TIMEOUT_S
        remaining = set(file_names)
        entries: dict[str, dict[str, Any]] = {}

        with httpx.Client(timeout=30) as client:
            while remaining and time.monotonic() < deadline:
                r = client.get(
                    f"{self.base_url}{BATCH_RESULT_PATH_TMPL.format(batch_id=batch_id)}",
                    headers=headers,
                )
                r.raise_for_status()
                payload = r.json()

                data = payload.get("data") or {}
                results = data.get("extract_result") or []
                for entry in results:
                    fname = entry.get("file_name", "")
                    if fname in remaining:
                        state = (entry.get("state") or "").lower()
                        if state in ("done", "success", "completed", "failed", "error", "cancelled"):
                            entries[fname] = entry
                            remaining.discard(fname)

                if remaining:
                    time.sleep(POLL_INTERVAL_S)

        return entries

    def _extract_text_from_entry(self, entry: dict[str, Any]) -> str:
        """Extract text from a completed MinerU result entry.

        If ``full_zip_url`` is present, download and extract the markdown
        from the ZIP. Otherwise fall back to inline fields.
        """
        # Prefer inline md_content
        md_content = entry.get("md_content") or ""
        if md_content.strip():
            return md_content

        # Fall back to downloading the result ZIP
        zip_url = entry.get("full_zip_url") or ""
        if not zip_url:
            # Try top-level data fields
            data = entry.get("data") or {}
            for key in ("full_md_link", "md_content", "content"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            return ""

        try:
            with httpx.Client(timeout=60) as client:
                r = client.get(zip_url)
                r.raise_for_status()
                with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                    # Find the markdown file inside the ZIP
                    md_files = [n for n in zf.namelist() if n.endswith(".md")]
                    if md_files:
                        return zf.read(md_files[0]).decode("utf-8")
                    # Fall back to any text file
                    txt_files = [n for n in zf.namelist() if n.endswith(".txt")]
                    if txt_files:
                        return zf.read(txt_files[0]).decode("utf-8")
        except Exception as exc:
            logger.warning("MinerU ZIP download/extract failed: %s", exc)

        return ""
