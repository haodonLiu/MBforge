"""Smoke test: verify setup_logging() can emit Unicode (✓/✗) even when
sys.stdout.encoding is something restrictive like gbk.

This reproduces the exact crash from the sidecar bug:
    UnicodeEncodeError: 'gbk' codec can't encode character '✓'
"""
import io
import logging
import sys

from mbforge.utils.logger import setup_logging


def test_unicode_emit_under_gbk_like_stdout():
    """Force stdout encoding to gbk (Windows zh-CN default) and emit ✓/✗."""
    # Simulate the worst case: stdout claims to be gbk and will raise on ✓
    fake_buf = io.BytesIO()
    gbk_stdout = io.TextIOWrapper(fake_buf, encoding="gbk", errors="strict")
    saved = sys.stdout
    sys.stdout = gbk_stdout
    try:
        setup_logging(level=logging.INFO, console=True, file=False)
        # The actual error trigger from model_server/main.py
        log = logging.getLogger("mbforge.startup")
        log.info("  ✓ resource A: ready at C:\\Users\\me")
        log.info("  ✗ resource B: missing")
        log.info("  ✓ resource C: ready")
    finally:
        sys.stdout = saved
    # If we got here without UnicodeEncodeError, the fix works. The test
    # passes by virtue of not raising. We deliberately do NOT log/print
    # the success marker: the original `print` used the real stdout
    # (outside the gbk-swap), so it didn't actually exercise the
    # encoding path and was dead weight per AGENTS.md "never print()".
