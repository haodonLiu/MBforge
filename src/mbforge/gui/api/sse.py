"""SSE streaming client for Agent chat and KB search."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable

import httpx

logger = logging.getLogger(__name__)


class SSEClient:
    """SSE client that runs in a background thread."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._active = False
        self._thread: threading.Thread | None = None

    def stop(self):
        self._active = False

    def stream_search(
        self,
        query: str,
        library_root: str,
        on_results: Callable[[list[dict]], None],
        on_done: Callable[[int], None],
        on_error: Callable[[str], None],
        top_k: int = 10,
    ):
        """Stream KB search results via SSE."""
        self._active = True

        def _worker():
            try:
                url = f"{self.base_url}/api/v1/kb/search/stream"
                params = {"query": query, "library_root": library_root, "top_k": top_k}
                with httpx.stream("GET", url, params=params, timeout=60) as resp:
                    for line in resp.iter_lines():
                        if not self._active:
                            break
                        if not line.startswith("data: "):
                            continue
                        try:
                            event = json.loads(line[6:])
                        except json.JSONDecodeError:
                            continue

                        event_type = event.get("type", "")
                        if event_type == "results":
                            on_results(event.get("results", []))
                        elif event_type == "done":
                            on_done(event.get("total", 0))
                        elif event_type == "error":
                            on_error(event.get("error", "Unknown error"))
            except Exception as e:
                logger.error("SSE search error: %s", e)
                on_error(str(e))

        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()

    def stream_chat(
        self,
        session_id: str,
        user_input: str,
        on_chunk: Callable[[str], None],
        on_tool_call: Callable[[str], None],
        on_done: Callable[[], None],
        on_error: Callable[[str], None],
    ):
        """Stream Agent chat response via SSE."""
        self._active = True

        def _worker():
            try:
                url = f"{self.base_url}/api/v1/agent/session/{session_id}/chat/stream"
                params = {"user_input": user_input}
                with httpx.stream("GET", url, params=params, timeout=120) as resp:
                    for line in resp.iter_lines():
                        if not self._active:
                            break
                        if not line.startswith("data: "):
                            continue
                        try:
                            event = json.loads(line[6:])
                        except json.JSONDecodeError:
                            continue

                        event_type = event.get("event", "")
                        if event_type == "chunk":
                            on_chunk(event.get("delta", ""))
                        elif event_type == "tool_call":
                            on_tool_call(event.get("tool", ""))
                        elif event_type == "done":
                            on_done()
                            return
                        elif event_type == "error":
                            on_error(event.get("error", "Unknown error"))
                            return
            except Exception as e:
                logger.error("SSE chat error: %s", e)
                on_error(str(e))

        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()
