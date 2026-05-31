from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MolScribeResult:
    esmiles: str
    confidence: float
    molfile: str = ""
    success: bool = True
    error: str = ""
