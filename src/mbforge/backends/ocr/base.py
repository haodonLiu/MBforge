"""Abstract OCR backend interface.

All cloud OCR backends expose a single synchronous entry point
`extract_text(image: bytes) -> str` so the fallback chain can call
them uniformly. Backends that are async (MinerU: submit + poll)
internally block until completion.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class OCRResult:
    """Outcome of a single OCR attempt.

    `text` is the extracted plain text (page-level). On failure,
    `text` is empty and `error` describes why.
    """

    text: str
    error: str | None = None


class OCRBackend(abc.ABC):
    """Base class for OCR backends."""

    #: Stable identifier used in settings & priority chain.
    name: str = ""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """Return True iff the backend has everything it needs to run."""

    @abc.abstractmethod
    def extract_text(self, image: bytes) -> OCRResult:
        """Run OCR on a single page image.

        `image` is PNG-encoded bytes (or whatever PyMuPDF produced).
        Implementations should raise on transport errors and return
        OCRResult(error=...) on logical failures (auth, quota, etc.)
        so the chain can fall through to the next backend.
        """
