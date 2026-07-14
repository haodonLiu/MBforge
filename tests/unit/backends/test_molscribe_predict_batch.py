"""Unit tests for MolScribe batch prediction."""

from __future__ import annotations

from unittest.mock import MagicMock

from mbforge.backends import molscribe as molscribe_module
from mbforge.backends.molscribe import predict_batch


def test_predict_batch_calls_backend_once_with_all_images(monkeypatch) -> None:
    """predict_batch passes every crop to _MODEL.predict_images in one call."""
    # Reset module singletons so we can install a fake model.
    molscribe_module._MODEL = None
    molscribe_module._AVAILABLE = False
    molscribe_module._ERROR = ""

    fake_backend = MagicMock()
    fake_backend.predict_images.return_value = [
        {"smiles": "C", "confidence": 0.9},
        {"smiles": "CC", "confidence": 0.8},
    ]

    molscribe_module._MODEL = fake_backend
    molscribe_module._AVAILABLE = True

    from PIL import Image

    images = [Image.new("L", (10, 10)), Image.new("L", (12, 12))]
    results = predict_batch(images)

    fake_backend.predict_images.assert_called_once()
    assert len(fake_backend.predict_images.call_args[0][0]) == 2
    assert len(results) == 2
    assert results[0].esmiles == "C"
    assert results[1].esmiles == "CC"


def test_predict_batch_handles_numpy_input(monkeypatch) -> None:
    """predict_batch converts numpy arrays to PIL before batching."""
    import numpy as np

    molscribe_module._MODEL = MagicMock()
    molscribe_module._MODEL.predict_images.return_value = [
        {"smiles": "C", "confidence": 0.9}
    ]
    molscribe_module._AVAILABLE = True

    images = [np.zeros((10, 10), dtype=np.uint8)]
    results = predict_batch(images)

    passed_images = molscribe_module._MODEL.predict_images.call_args[0][0]
    assert len(passed_images) == 1
    assert passed_images[0].size == (10, 10)
    assert results[0].esmiles == "C"
