"""Unit tests for backends.ocr.rapidocr_adapter.RapidOCRCropAdapter.

The real RapidOCR engine is heavy (~1s to load, ONNX models) and not
suitable for fast unit tests. We mock the engine at the
``RapidOCR.__call__`` boundary so the test suite stays fast and
deterministic. The integration test in test_coref_ocr_integration.py
exercises the full path through routers/coref.py with the same mock.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from mbforge.backends.ocr.rapidocr_adapter import RapidOCRCropAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine_mock(per_call: list[list[tuple[str, float]]] | None = None):
    """Build a MagicMock that mimics a RapidOCR engine.

    Each call consumes one entry from ``per_call`` and returns it as
    a RapidOCROutput-like object. If per_call is exhausted, returns
    None (no text). If per_call is None, returns a single-text result
    for every call.
    """
    calls = [0]  # mutable for closure

    def _call(img, use_det=None, use_rec=None):
        idx = calls[0]
        calls[0] += 1
        if per_call is None:
            txts = ["text"]
            scores = [0.9]
        elif idx >= len(per_call):
            return None
        else:
            lines = per_call[idx]
            txts = [t for t, _ in lines]
            scores = [s for _, s in lines]
        out = MagicMock()
        out.txts = txts
        out.scores = scores
        return out

    engine = MagicMock()
    engine.side_effect = _call
    return engine


@pytest.fixture(autouse=True)
def reset_adapter_singleton():
    """Reset the adapter singleton before and after each test."""
    RapidOCRCropAdapter.reset()
    yield
    RapidOCRCropAdapter.reset()


def _inject_mock_engine(engine: MagicMock) -> None:
    """Patch the adapter to use a mock engine without loading ONNX."""
    RapidOCRCropAdapter._instance = RapidOCRCropAdapter.__new__(
        RapidOCRCropAdapter
    )
    RapidOCRCropAdapter._instance._engine = engine
    RapidOCRCropAdapter._init_error = None


# ---------------------------------------------------------------------------
# read_one_sync tests
# ---------------------------------------------------------------------------


def test_read_one_returns_top_text():
    engine = _make_engine_mock(per_call=[[("Ia", 0.9)]])
    _inject_mock_engine(engine)
    adapter = RapidOCRCropAdapter.instance()
    img = Image.new("RGB", (32, 16), (255, 255, 255))
    assert adapter._read_one_sync(img) == "Ia"


def test_read_one_empty_when_engine_returns_none():
    engine = MagicMock()
    engine.side_effect = lambda *a, **kw: None
    _inject_mock_engine(engine)
    adapter = RapidOCRCropAdapter.instance()
    img = Image.new("RGB", (32, 16), (255, 255, 255))
    assert adapter._read_one_sync(img) == ""


def test_read_one_picks_highest_score_line():
    # Engine returns 3 lines; we want the highest-score one.
    engine = _make_engine_mock(
        per_call=[[("low", 0.3), ("WIN", 0.95), ("mid", 0.6)]]
    )
    _inject_mock_engine(engine)
    adapter = RapidOCRCropAdapter.instance()
    img = Image.new("RGB", (32, 16), (255, 255, 255))
    assert adapter._read_one_sync(img) == "WIN"


def test_read_one_falls_back_to_first_line_when_scores_mismatch():
    # Scores list shorter than txts - defensive code should not crash.
    out = MagicMock()
    out.txts = ["only_txt"]
    out.scores = []  # empty scores
    engine = MagicMock()
    engine.side_effect = lambda *a, **kw: out
    _inject_mock_engine(engine)
    adapter = RapidOCRCropAdapter.instance()
    img = Image.new("RGB", (32, 16), (255, 255, 255))
    assert adapter._read_one_sync(img) == "only_txt"


def test_read_one_returns_empty_on_engine_exception():
    engine = MagicMock()
    engine.side_effect = RuntimeError("ONNX inference failed")
    _inject_mock_engine(engine)
    adapter = RapidOCRCropAdapter.instance()
    img = Image.new("RGB", (32, 16), (255, 255, 255))
    assert adapter._read_one_sync(img) == ""


# ---------------------------------------------------------------------------
# readtext_batch tests
# ---------------------------------------------------------------------------


def test_readtext_batch_empty():
    engine = _make_engine_mock()
    _inject_mock_engine(engine)
    adapter = RapidOCRCropAdapter.instance()
    assert adapter.readtext_batch([]) == []


def test_readtext_batch_preserves_order():
    # Engine returns different text per call; result order must match input order.
    engine = _make_engine_mock(
        per_call=[
            [("alpha", 0.9)],
            [("beta", 0.8)],
            [("gamma", 0.7)],
            [("delta", 0.6)],
        ]
    )
    _inject_mock_engine(engine)
    adapter = RapidOCRCropAdapter.instance()
    images = [Image.new("RGB", (16, 16), (255, 255, 255)) for _ in range(4)]
    result = adapter.readtext_batch(images, max_workers=2)
    assert result == ["alpha", "beta", "gamma", "delta"]


def test_readtext_batch_partial_failure_returns_empty_strings():
    # Mixed: call 0 returns text, call 1 returns None, call 2 returns text.
    call_count = [0]

    def _side(img, use_det=None, use_rec=None):
        idx = call_count[0]
        call_count[0] += 1
        if idx == 1:
            return None
        out = MagicMock()
        out.txts = [f"text_{idx}"]
        out.scores = [0.9]
        return out

    engine = MagicMock()
    engine.side_effect = _side
    _inject_mock_engine(engine)
    adapter = RapidOCRCropAdapter.instance()
    images = [Image.new("RGB", (16, 16), (255, 255, 255)) for _ in range(3)]
    result = adapter.readtext_batch(images, max_workers=2)
    assert result == ["text_0", "", "text_2"]


def test_readtext_batch_concurrency_runs_in_parallel():
    """Sanity: 4 images x 50ms each should complete in well under 200ms
    if running on 4 workers, proving ThreadPoolExecutor actually parallelizes.

    We sleep 50ms inside the engine to simulate inference latency.
    """
    sleep_seconds = 0.05

    def _slow(img, use_det=None, use_rec=None):
        time.sleep(sleep_seconds)
        out = MagicMock()
        out.txts = ["x"]
        out.scores = [0.9]
        return out

    engine = MagicMock()
    engine.side_effect = _slow
    _inject_mock_engine(engine)
    adapter = RapidOCRCropAdapter.instance()
    images = [Image.new("RGB", (16, 16), (255, 255, 255)) for _ in range(4)]

    t0 = time.perf_counter()
    result = adapter.readtext_batch(images, max_workers=4)
    elapsed = time.perf_counter() - t0

    assert result == ["x", "x", "x", "x"]
    # 4 workers x 50ms each in parallel should take ~50ms not 200ms.
    # Allow generous margin (200ms) for CI scheduling overhead.
    assert elapsed < 0.2, (
        f"4 concurrent 50ms calls took {elapsed*1000:.0f}ms - "
        "ThreadPoolExecutor is not parallelizing"
    )


# ---------------------------------------------------------------------------
# Async wrapper test
# ---------------------------------------------------------------------------



def test_readtext_batch_async_returns_same_as_sync():
    # Build an engine that returns the same per-index text on every call
    # so that sync and async paths both produce the expected result
    # (the per_call list is shared, so reusing it across two batched
    # invocations would exhaust it; we re-create the response each call).
    def _factory(img, use_det=None, use_rec=None):
        # Identify which call this is by an attribute on the mock image.
        # The image is a PIL Image; the adapter does not set custom
        # attributes, so we just alternate via a counter.
        try:
            _factory.counter += 1
        except AttributeError:
            _factory.counter = 0
        idx = _factory.counter
        out = MagicMock()
        out.txts = ["one" if idx == 0 or idx == 2 else "two"]
        out.scores = [0.9]
        return out

    engine = MagicMock()
    engine.side_effect = _factory
    _inject_mock_engine(engine)
    adapter = RapidOCRCropAdapter.instance()
    images = [Image.new("RGB", (16, 16), (255, 255, 255)) for _ in range(2)]
    sync_result = adapter.readtext_batch(images, max_workers=2)
    async_result = asyncio.run(
        adapter.readtext_batch_async(images, max_workers=2)
    )
    # 4 calls total: sync batch [one, two] and async batch [one, two]
    assert sync_result == ["one", "two"]
    assert async_result == ["one", "two"]
def test_singleton_returns_same_instance():
    engine = _make_engine_mock()
    _inject_mock_engine(engine)
    a = RapidOCRCropAdapter.instance()
    b = RapidOCRCropAdapter.instance()
    assert a is b


def test_reset_allows_re_init():
    RapidOCRCropAdapter._instance = RapidOCRCropAdapter.__new__(
        RapidOCRCropAdapter
    )
    RapidOCRCropAdapter._instance._engine = _make_engine_mock()
    assert RapidOCRCropAdapter.is_available()
    RapidOCRCropAdapter.reset()
    assert not RapidOCRCropAdapter.is_available()


def test_init_failure_caches_error_and_raises_consistently():
    """If the engine constructor fails, subsequent instance() calls
    raise the same error (not re-attempting construction)."""
    RapidOCRCropAdapter.reset()
    with patch.object(RapidOCRCropAdapter, "__init__", side_effect=ImportError("no rapidocr")):
        with pytest.raises(ImportError, match="no rapidocr"):
            RapidOCRCropAdapter.instance()
        # Second call also raises (cached error).
        with pytest.raises(ImportError, match="no rapidocr"):
            RapidOCRCropAdapter.instance()



def test_instance_concurrent_calls_return_same_singleton():
    """Thread-safety check: 8 threads racing on first instance() must
    all get the same object. Without the init lock, two threads could
    both construct the engine and the loser would silently overwrite
    the winner's state.
    """
    import threading

    engine = _make_engine_mock()
    _inject_mock_engine(engine)

    # We need to actually race on the instance() call (not on a
    # pre-injected _instance), so reset and re-inject AFTER the barrier.
    RapidOCRCropAdapter.reset()

    results: list[RapidOCRCropAdapter] = []
    errors: list[BaseException] = []
    n_threads = 8
    barrier = threading.Barrier(n_threads)

    def worker() -> None:
        try:
            # All threads wait at the barrier so they all call
            # instance() within microseconds of each other.
            barrier.wait(timeout=5)
            results.append(RapidOCRCropAdapter.instance())
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"worker threads raised: {errors}"
    assert len(results) == n_threads
    # All threads must have gotten the same object.
    first = results[0]
    assert all(r is first for r in results), (
        f"concurrent instance() returned {len(set(map(id, results)))} "
        "distinct objects — the init lock is broken"
    )
