#!/usr/bin/env python3
"""下载 MolScribe 模型权重（仅推理所需的 1 个 checkpoint，约 1GB）.

用法: python setup/download_molscribe.py
"""

import sys
sys.path.insert(0, "src")

from mbforge.parsers.molecule.molscribe_inference.download import ensure_molscribe_model

try:
    path = ensure_molscribe_model()
    print(f"OK MolScribe: {path}")
except RuntimeError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
