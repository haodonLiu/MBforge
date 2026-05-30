"""MolScribe inference module (stripped from original for MBForge).

Only retains inference-path code. No training, no albumentations, no indigo.
"""

from .interface import MolScribe

__all__ = ["MolScribe"]
