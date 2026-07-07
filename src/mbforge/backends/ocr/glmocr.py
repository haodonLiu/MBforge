"""GLM-OCR backend (Zhipu AI).

Endpoint:
  POST https://open.bigmodel.cn/api/paas/v4/layout_parsing
  Headers: Authorization: Bearer <api_key>
  Body (JSON):
    {
      "model": "glm-ocr",
      "document": {"type": "image_url", "image_url": "data:image/png;base64,..."}
    }

Response shape (typical):
  {
    "choices": [{
      "message": {
        "content": "<markdown or text>",
        "reasoning_content": "..."
      }
    }]
  }
"""

from __future__ import annotations

import base64
import logging

import httpx

from .base import OCRBackend, OCRResult

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
LAYOUT_PARSING_PATH = "/layout_parsing"


class GLMOCRBackend(OCRBackend):
    name = "glmocr"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        cfg = config or {}
        self.api_key: str = cfg.get("api_key", "").strip()
        base_url = cfg.get("base_url", "").strip() or DEFAULT_BASE_URL
        self.base_url = base_url.rstrip("/")
        self.model: str = cfg.get("model", "glm-ocr").strip() or "glm-ocr"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def extract_text(self, image: bytes) -> OCRResult:
        if not self.is_configured():
            return OCRResult(text="", error="GLM-OCR api_key not set")
        data_url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
        body = {"model": self.model, "document": {"type": "image_url", "image_url": data_url}}
        try:
            with httpx.Client(timeout=60) as client:
                r = client.post(
                    f"{self.base_url}{LAYOUT_PARSING_PATH}",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                r.raise_for_status()
                payload = r.json()
            text = self._extract_text(payload)
            return OCRResult(text=text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("GLM-OCR failed: %s", exc)
            return OCRResult(text="", error=str(exc))

    @staticmethod
    def _extract_text(payload: dict) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        # `content` is the rendered markdown/text.
        # `reasoning_content` (if any) is internal chain-of-thought — skip.
        content = message.get("content")
        if isinstance(content, str):
            return content
        # Some proxies return `{"text": "..."}` instead of OpenAI shape.
        if isinstance(message.get("text"), str):
            return message["text"]
        return ""
