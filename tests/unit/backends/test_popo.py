"""Unit tests for the MinerU-Popo backend driver invocation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from mbforge.backends import popo


@pytest.fixture(autouse=True)
def _reset_popo_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate Popo state across tests."""
    monkeypatch.delenv("POPO_MODEL_PATH", raising=False)
    monkeypatch.delenv("POPO_CONFIG_PATH", raising=False)


@pytest.fixture
def fake_popo_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a minimal fake MinerU-Popo install and model directory."""
    install_dir = tmp_path / "MinerU-Popo"
    install_dir.mkdir(parents=True, exist_ok=True)
    (install_dir / "post_processing").mkdir()
    (install_dir / "post_processing" / "model_utils.py").write_text("# stub")

    model_dir = tmp_path / "models" / "MinerU-Popo"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "config.json").write_text('{"model_type": "qwen3_vl"}')

    monkeypatch.setattr(popo, "POPO_INSTALL_DIR", install_dir)
    monkeypatch.setattr(popo, "_DRIVER_PATH", install_dir / "_mbforge_driver.py")
    monkeypatch.setenv("POPO_MODEL_PATH", str(model_dir))
    return install_dir


def test_popo_installed_false_when_missing() -> None:
    """popo_installed returns False when the install directory is absent."""
    assert popo.popo_installed() is False


def test_popo_postprocess_skips_when_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """popo_postprocess_markdown returns None when Popo is not installed."""
    monkeypatch.setattr(popo, "popo_installed", lambda: False)
    assert popo.popo_postprocess_markdown("# hello") is None


def test_popo_postprocess_skips_when_model_path_missing(
    fake_popo_install: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """popo_postprocess_markdown returns None when the model path is missing."""
    monkeypatch.setenv("POPO_MODEL_PATH", str(fake_popo_install / "no-such-model"))
    assert popo.popo_postprocess_markdown("# hello") is None


def test_popo_postprocess_writes_static_driver(
    fake_popo_install: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A static driver is written and invoked; config is passed via JSON file."""
    driver_path = fake_popo_install / "_mbforge_driver.py"

    captured: dict[str, Any] = {}

    def _fake_run(
        cmd: list[str],
        *,
        input: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        captured["input"] = input
        captured["cwd"] = cwd
        captured["env"] = env
        config_path = env.get("POPO_CONFIG_PATH") if env else None
        captured["config_path"] = config_path
        if config_path:
            captured["config"] = json.loads(
                Path(config_path).read_text(encoding="utf-8")
            )
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="enhanced markdown",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = popo.popo_postprocess_markdown("# original", image_b64="b64data")

    assert result == "enhanced markdown"
    assert driver_path.exists()
    driver_source = driver_path.read_text(encoding="utf-8")
    assert "POPO_CONFIG_PATH" in driver_source
    # The driver must be the static template, not generated per-call.
    assert driver_source == popo._POPO_DRIVER_SOURCE

    config = captured["config"]
    assert Path(config["model_path"]).exists()
    assert config["image_b64"] == "b64data"
    assert config["max_new_tokens"] == 2048


def test_popo_postprocess_cleans_up_config_file(
    fake_popo_install: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The temporary JSON config file is removed after the subprocess runs."""
    config_paths: list[Path] = []

    def _fake_run(
        cmd: list[str],
        *,
        input: str | None = None,
        capture_output: bool = False,
        text: bool = False,
        timeout: int | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        config_paths.append(Path(env["POPO_CONFIG_PATH"]))
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="ok",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    popo.popo_postprocess_markdown("text")
    assert len(config_paths) == 1
    assert not config_paths[0].exists()


def test_popo_postprocess_returns_none_on_nonzero_exit(
    fake_popo_install: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-zero subprocess exit code yields None."""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="model failed",
        ),
    )
    assert popo.popo_postprocess_markdown("# original") is None


def test_popo_postprocess_returns_none_on_timeout(
    fake_popo_install: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A subprocess timeout yields None."""

    def _raise_timeout(*_args: Any, **_kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(cmd="popo", timeout=1)

    monkeypatch.setattr(subprocess, "run", _raise_timeout)
    assert popo.popo_postprocess_markdown("# original") is None


def test_ensure_driver_rewrites_stale_driver(
    fake_popo_install: Path,
) -> None:
    """_ensure_driver overwrites the driver if its contents differ."""
    driver_path = fake_popo_install / "_mbforge_driver.py"
    driver_path.write_text("# stale driver", encoding="utf-8")

    popo._ensure_driver()

    assert driver_path.read_text(encoding="utf-8") == popo._POPO_DRIVER_SOURCE
