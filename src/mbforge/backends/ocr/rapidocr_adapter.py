"""RapidOCR crop-level adapter (not page-level — use OCRBackend for that).

Restored 2026-07-09 to support the coref bridge (routers/coref.py).
Provides single-crop and batch (concurrent) recognition by running the
underlying RapidOCR engine with ``use_det=False`` to skip the detector
(crops are pre-bounded by the FT detector).

The previous home for this class was ``parsers/molecule/coref_alt.py``
(``_RapidOCRAdapter``), but it was deleted in the 2026-07-08 FT
migration along with the rest of the moldet+OCR path. This file
reintroduces it as a singleton under ``backends/ocr/`` so both the
OCR chain (page-level, via ``RapidOCRBackend``) and the coref bridge
(crop-level, this module) share the same engine instance.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class RapidOCRCropAdapter:
    """Crop-level RapidOCR adapter. Singleton; not a page OCRBackend.

    Construction is lazy (singleton on first ``instance()`` call) because
    loading the ONNX models takes ~1s and we don't want to pay that
    cost at import time.
    """

    _instance: RapidOCRCropAdapter | None = None
    _init_error: BaseException | None = None
    # Guards first-time construction. The check-then-act in instance()
    # below is racy without this lock; the FastAPI single-thread case
    # happens to be safe, but a callable from a worker / script / test
    # thread is not. Use double-checked locking so the fast path
    # (instance already built) stays lock-free.
    _init_lock: threading.Lock | None = None

    @classmethod
    def instance(cls) -> RapidOCRCropAdapter:
        """Return the process-wide singleton, building it on first call.

        Thread-safe via double-checked locking: the fast path (instance
        already built) is lock-free, the slow path acquires the lock
        and re-checks the condition. The cached init error is raised on
        every subsequent call if the very first attempt to build the
        singleton failed (e.g. rapidocr not installed). Callers that
        want graceful fallback should use ``is_available()`` first, or
        wrap the call in try/except.
        """
        # Fast path: already built and no error cached.
        if cls._instance is not None:
            return cls._instance
        # Slow path: acquire the lock, re-check, then build.
        # The lock is lazily created to avoid a module-level Lock
        # object before the class body is fully defined.
        if cls._init_lock is None:
            cls._init_lock = threading.Lock()
        with cls._init_lock:
            if cls._instance is None and cls._init_error is None:
                try:
                    cls._instance = cls()
                except Exception as e:  # noqa: BLE001 - capture any load failure
                    cls._init_error = e
                    logger.warning(
                        "RapidOCRCropAdapter failed to initialize: %s. "
                        "Label text will fall back to synthetic placeholders.",
                        e,
                    )
        if cls._init_error is not None:
            raise cls._init_error
        assert cls._instance is not None  # post-condition of the build branch
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (used in tests to force re-init).

        Acquires the init lock to ensure a concurrent ``instance()`` call
        cannot leave us with a half-cleared state.
        """
        if cls._init_lock is None:
            cls._init_lock = threading.Lock()
        with cls._init_lock:
            cls._instance = None
            cls._init_error = None

    def __init__(self) -> None:
        from rapidocr import (  # local import: keep optional
            EngineType,
            LangDet,
            LangRec,
            ModelType,
            OCRVersion,
            RapidOCR,
        )

        self._engine = RapidOCR(
            params={
                "Det.engine_type": EngineType.ONNXRUNTIME,
                "Det.lang_type": LangDet.EN,
                "Det.model_type": ModelType.MEDIUM,
                "Det.ocr_version": OCRVersion.PPOCRV6,
                "Det.use_dml": True,
                "Rec.engine_type": EngineType.ONNXRUNTIME,
                "Rec.lang_type": LangRec.EN,
                "Rec.model_type": ModelType.MEDIUM,
                "Rec.ocr_version": OCRVersion.PPOCRV6,
                "Rec.use_dml": True,
            }
        )

    # ---- single-crop worker (used by both sync and async paths) ----

    def _read_one_sync(self, image: Image.Image) -> str:
        """Run recognizer on a single crop; return top-score text or "".

        Uses ``use_det=False`` so the engine treats the input as an
        already-cropped text region and only runs the recognizer.
        Returns the highest-score text line, or "" if the engine
        produces no text (empty page, blank crop, etc.).
        """
        try:
            arr = np.array(image.convert("RGB"))
        except Exception as e:  # noqa: BLE001 - bad input image
            logger.debug("RapidOCR crop convert failed: %s", e)
            return ""
        try:
            out = self._engine(arr, use_det=False, use_rec=True)
        except Exception as e:  # noqa: BLE001 - inference can fail on weird crops
            logger.debug("RapidOCR inference failed: %s", e)
            return ""
        if not out or not getattr(out, "txts", None):
            return ""
        txts = [t for t in out.txts if t]
        if not txts:
            return ""
        scores = list(out.scores or [])
        if scores and len(scores) == len(txts):
            idx = max(range(len(txts)), key=lambda i: scores[i])
            return txts[idx]
        return txts[0]

    # ---- public batch API ----

    def readtext_batch(
        self,
        images: list[Image.Image],
        max_workers: int = 4,
    ) -> list[str]:
        """Run recognizer on N crops concurrently.

        Concurrency model: ThreadPoolExecutor. ONNX Runtime releases the
        GIL during inference so threads give real parallelism. Capped at
        4 workers to avoid oversubscribing the GPU when DML is in use.
        Order of the returned list matches order of input images.
        """
        if not images:
            return []
        workers = min(max_workers, len(images))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(self._read_one_sync, images))

    async def readtext_batch_async(
        self,
        images: list[Image.Image],
        max_workers: int = 4,
    ) -> list[str]:
        """Async wrapper for use inside FastAPI request handlers."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.readtext_batch(images, max_workers=max_workers),
        )

    @classmethod
    def is_available(cls) -> bool:
        """True if the singleton was built without error."""
        return cls._instance is not None and cls._init_error is None
