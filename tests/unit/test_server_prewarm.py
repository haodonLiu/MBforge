"""Tests for server.py model prewarm."""
from unittest.mock import patch

from mbforge.server import _prewarm


class TestPrewarm:
    def test_prewarm_calls_moldet_and_molscribe(self):
        with (
            patch("mbforge.backends.moldet_v2_ft.get_moldet_ft") as mock_moldet,
            patch("mbforge.backends.molscribe.load") as mock_molscribe,
        ):
            _prewarm()
        mock_moldet.assert_called_once()
        mock_molscribe.assert_called_once()

    def test_prewarm_continues_after_moldet_failure(self):
        with (
            patch("mbforge.backends.moldet_v2_ft.get_moldet_ft") as mock_moldet,
            patch("mbforge.backends.molscribe.load") as mock_molscribe,
        ):
            mock_moldet.side_effect = RuntimeError("model not found")
            _prewarm()
        mock_moldet.assert_called_once()
        mock_molscribe.assert_called_once()

    def test_prewarm_continues_after_molscribe_failure(self):
        with (
            patch("mbforge.backends.moldet_v2_ft.get_moldet_ft") as mock_moldet,
            patch("mbforge.backends.molscribe.load") as mock_molscribe,
        ):
            mock_molscribe.side_effect = RuntimeError("model not found")
            _prewarm()
        mock_moldet.assert_called_once()
        mock_molscribe.assert_called_once()
