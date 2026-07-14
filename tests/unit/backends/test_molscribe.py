from __future__ import annotations

import threading

from mbforge.backends import molscribe as molscribe_module
from mbforge.backends.molscribe import load


class _FakeMolScribe:
    """Stand-in for the heavy MolScribe backend constructor."""

    def __init__(self, path: str, device: str, num_workers: int) -> None:
        self.path = path
        self.device = device
        self.num_workers = num_workers

    def predict_images(self, images):
        return [{"smiles": "C", "confidence": 0.9}]


def test_load_concurrent_first_call_creates_single_model(monkeypatch):
    """Concurrent first calls to molscribe.load create only one model instance."""
    # Reset module singletons so this test observes first-call behavior.
    molscribe_module._MODEL = None
    molscribe_module._AVAILABLE = False
    molscribe_module._ERROR = ""

    construct_count = {"n": 0}
    count_lock = threading.Lock()

    def _fake_init(self, path, device, num_workers):
        with count_lock:
            construct_count["n"] += 1
        self.path = path
        self.device = device
        self.num_workers = num_workers

    fake_molscribe = type(
        "FakeMolScribe",
        (),
        {
            "__init__": _fake_init,
            "predict_images": lambda self, images: [{"smiles": "C", "confidence": 0.9}],
        },
    )
    monkeypatch.setattr(
        "mbforge.parsers.molecule.molscribe_inference.MolScribe",
        fake_molscribe,
    )
    monkeypatch.setattr(
        molscribe_module,
        "is_gpu_available",
        lambda: False,
    )
    monkeypatch.setattr(
        "mbforge.core.resource_manager.ResourceManager.get_molscribe_path",
        staticmethod(lambda: "/fake/path.ckpt"),
    )

    models = []
    result_lock = threading.Lock()

    def _target():
        load()
        with result_lock:
            models.append(molscribe_module._MODEL)

    threads = [threading.Thread(target=_target) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len({id(m) for m in models}) == 1
    assert construct_count["n"] == 1
