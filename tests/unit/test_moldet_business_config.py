"""Model inference settings must come from persisted application settings."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from mbforge.backends.moldet_v2_ft import MolDetv2FTDetector
from mbforge.parsers.molecule.molscribe_inference.download import get_model_dir
from mbforge.utils.config import AppConfig, MoldetConfig


def test_molscribe_directory_ignores_legacy_environment_override(
    monkeypatch,
    tmp_path: Path,
) -> None:
    configured_dir = tmp_path / "configured-molscribe"
    monkeypatch.setenv("MBFORGE_MOLSCRIBE_DIR", str(tmp_path / "environment"))
    config = AppConfig(moldet=MoldetConfig(molscribe_dir=str(configured_dir)))

    with patch(
        "mbforge.parsers.molecule.molscribe_inference.download.load_global_config",
        return_value=config,
    ):
        assert get_model_dir() == configured_dir


def test_moldet_device_ignores_legacy_environment_override(monkeypatch) -> None:
    monkeypatch.setenv("MBFORGE_DEVICE", "cuda:99")
    config = AppConfig(moldet=MoldetConfig(device="cpu"))

    with (
        patch("mbforge.backends.moldet_v2_ft._has_ultralytics", return_value=True),
        patch.object(MolDetv2FTDetector, "_load_model"),
        patch(
            "mbforge.backends.moldet_v2_ft.load_global_config",
            return_value=config,
        ),
    ):
        detector = MolDetv2FTDetector(model_path=Path("weights.pt"))

    assert detector.device == "cpu"
