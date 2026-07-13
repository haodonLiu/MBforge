from __future__ import annotations

import threading

from mbforge.backends import moldet_v2_ft as moldet_module
from mbforge.backends.moldet_v2_ft import get_moldet_ft


def test_get_moldet_ft_concurrent_first_call_creates_single_instance(monkeypatch):
    """Concurrent first calls to get_moldet_ft create only one detector instance."""
    # Reset singleton so this test observes first-call behavior.
    moldet_module._detector_singleton = None

    load_count = {"n": 0}
    count_lock = threading.Lock()

    def _fake_load_model(self):
        with count_lock:
            load_count["n"] += 1
        self.model = "fake-model"

    monkeypatch.setattr(moldet_module.MolDetv2FTDetector, "_load_model", _fake_load_model)

    detectors = []
    result_lock = threading.Lock()

    def _target():
        detector = get_moldet_ft()
        with result_lock:
            detectors.append(detector)

    threads = [threading.Thread(target=_target) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len({id(d) for d in detectors}) == 1
    assert load_count["n"] == 1
