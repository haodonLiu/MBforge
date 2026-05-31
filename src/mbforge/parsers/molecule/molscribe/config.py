from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MolScribeConfig:
    model_path: str | Path | None = None
    device: str = "auto"
    batch_size: int = 16
    num_workers: int = 1
    timeout: float = 30.0
    log_smiles: bool = False
