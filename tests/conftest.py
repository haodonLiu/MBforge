"""Pytest configuration: ensure tests never pollute the real global settings.

The MBForge backend uses a single ``settings.json`` under the OS user-config
directory. Tests that exercise routers or other config-touching code paths
must NEVER write to that file — otherwise a failed/aborted test can leave
the user's ``library_root`` pointing at a deleted ``pytest-*`` tmp dir,
which silently breaks the dev workflow.

This conftest provides two autouse fixtures:

1. ``_isolate_global_state`` (function scope): per-test isolation. Redirects
   ``_SETTINGS_PATH`` to a tmp file, pre-writes ``library_root`` so library
   code paths operate on a tmp dir rather than ``~/mbforge``, clears every
   singleton cache, and wraps ``save_global_config`` so any code path that
   bypasses the monkeypatch is still routed through the tmp file.

2. ``_snapshot_real_settings`` (session scope): snapshots the real
   ``settings.json`` at the start of the test run and restores it byte-for-
   byte at the end. This is a safety net for any test that might somehow
   write to the real path despite the per-test isolation.

Tests that need their own isolated settings path (e.g. ``test_config.py``)
should declare their own ``tmp_settings``/``monkeypatch.setattr`` for
``_SETTINGS_PATH``; pytest's autouse-first ordering means the test's own
fixture still runs after this one and wins the monkeypatch.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest


def _real_settings_path() -> Path:
    from platformdirs import user_config_dir

    return Path(user_config_dir("MBForge", appauthor=False)) / "settings.json"


REAL_SETTINGS_PATH = _real_settings_path()


@pytest.fixture(autouse=True)
def _isolate_global_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Per-test isolation of the global settings.json + singleton caches.

    See module docstring for the rationale.
    """
    import mbforge.core.database
    import mbforge.core.library
    import mbforge.utils.config as cfg_mod

    # 1) Redirect settings writes to a tmp file for the duration of this test.
    fake_settings = tmp_path / "settings.json"
    monkeypatch.setattr(cfg_mod, "_SETTINGS_PATH", fake_settings)

    # 1a) Pre-write a settings.json that points library_root at a tmp library.
    # This ensures library-touching code paths (status, import) operate on
    # the tmp dir rather than defaulting to ~/mbforge, which would pollute
    # the user's real library. Tests that want to exercise migration from
    # legacy config files (test_config.TestMigration) explicitly delete or
    # overwrite this file via their own tmp_settings fixture.
    test_library = tmp_path / "library"
    test_library.mkdir()
    fake_settings.write_text(
        '{"library_root": "%s"}' % str(test_library).replace("\\", "\\\\"),
        encoding="utf-8",
    )

    # 2) Also guard the legacy migration paths so any code that touches them
    #    in this test writes into tmp_path too.
    monkeypatch.setattr(
        cfg_mod,
        "_LEGACY_PATHS",
        (tmp_path / "config.json", tmp_path / "gui_state.json"),
    )

    # 3) Clear every singleton cache that depends on the settings file.
    cfg_mod.load_global_config.cache_clear()
    mbforge.core.database._db_cache.clear()
    mbforge.core.library._store_cache.clear()

    # 4) Belt-and-braces: if any code path bypasses the monkeypatch (e.g.
    #    imports a resolved Path at module load), it should still fail loud
    #    rather than corrupt user state. We wrap save_global_config so it
    #    refuses to write anywhere under REAL_SETTINGS_PATH.parent.
    real_dir = REAL_SETTINGS_PATH.parent.resolve()
    real_dir_str = str(real_dir)
    fake_resolved = fake_settings.resolve()

    def _guarded_save(config) -> None:  # type: ignore[no-untyped-def]
        target = cfg_mod._SETTINGS_PATH  # type: ignore[attr-defined]
        try:
            target_resolved = target.resolve()
        except OSError:
            target_resolved = target
        if (
            str(target_resolved).startswith(real_dir_str)
            and target_resolved != fake_resolved
        ):
            raise RuntimeError(
                f"Refusing to write to real user settings path {target_resolved}. "
                f"Tests must monkeypatch _SETTINGS_PATH before calling save_global_config."
            )
        cfg_mod.load_global_config.cache_clear()
        from mbforge.utils.helpers import save_json

        save_json(target, config.model_dump())

    monkeypatch.setattr(cfg_mod, "save_global_config", _guarded_save)

    yield

    # 5) Post-test: clear caches again so the next test starts from a clean state.
    cfg_mod.load_global_config.cache_clear()
    mbforge.core.database._db_cache.clear()
    mbforge.core.library._store_cache.clear()


@pytest.fixture(autouse=True, scope="session")
def _snapshot_real_settings() -> Generator[None, None, None]:
    """Snapshot the real settings.json before any test runs, restore after.

    This is a safety net: even if the per-test isolation ever has a hole,
    the user's real settings.json is restored byte-for-byte at the end of
    the test session.
    """
    snapshot_path: Path | None = None
    if REAL_SETTINGS_PATH.exists():
        snapshot_path = REAL_SETTINGS_PATH.with_suffix(".json.test-snapshot")
        try:
            shutil.copy2(REAL_SETTINGS_PATH, snapshot_path)
        except OSError:
            snapshot_path = None

    yield

    if snapshot_path and snapshot_path.exists():
        try:
            shutil.copy2(snapshot_path, REAL_SETTINGS_PATH)
            snapshot_path.unlink()
        except OSError:
            pass


def pytest_configure(config: pytest.Config) -> None:
    """Mark a flag in os.environ so production code can refuse to run during tests.

    Production modules that should never execute during pytest can check
    ``os.environ.get("MBFORGE_TESTING")`` and skip themselves.
    """
    os.environ.setdefault("MBFORGE_TESTING", "1")