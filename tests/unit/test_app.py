"""Tests for the FastAPI application lifespan and wiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_lifespan_awaits_prewarm_futures() -> None:
    """The lifespan context manager must await prewarm before yielding."""
    from mbforge.app import lifespan

    app = MagicMock()

    check_environment_mock = MagicMock()
    prewarm_mock = MagicMock()

    with (
        patch("mbforge.utils.helpers.check_environment", check_environment_mock),
        patch("mbforge.server._prewarm", prewarm_mock),
        patch("mbforge.utils.helpers.shutdown_backends") as shutdown_mock,
    ):
        async with lifespan(app):
            # By the time we enter the context body, both helpers must have run.
            check_environment_mock.assert_called_once()
            prewarm_mock.assert_called_once()
            shutdown_mock.assert_not_called()

        shutdown_mock.assert_called_once()
