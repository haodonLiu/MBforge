"""MBForge 打包脚本.

使用 PyInstaller 打包为独立 EXE。
用法:
    uv run python build.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def clean_build():
    """清理构建目录."""
    for d in ("build", "dist"):
        if os.path.isdir(d):
            shutil.rmtree(d)
            print(f"Removed {d}/")


def run_pyinstaller():
    """运行 PyInstaller."""
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name", "MBForge",
        "--onefile",
        "--windowed",
        "--icon", "NONE",
        "--add-data", f"src{os.pathsep}src",
        "--hidden-import", "pkg_resources",
        "--hidden-import", "markdown",
        "--hidden-import", "markdown.extensions.tables",
        "--hidden-import", "markdown.extensions.fenced_code",
        "--hidden-import", "markdown.extensions.toc",
        "--hidden-import", "markdown.extensions.nl2br",
        "--hidden-import", "chromadb",
        "--hidden-import", "sentence_transformers",
        "--hidden-import", "openai",
        "--hidden-import", "fitz",
        "--hidden-import", "PyQt6.QtWebEngineCore",
        "--hidden-import", "PyQt6.QtWebEngineWidgets",
        "--collect-all", "chromadb",
        "--collect-all", "sentence_transformers",
        "--collect-all", "rdkit",
        "src/mbforge/cli.py",
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    clean_build()
    run_pyinstaller()
    print("Build complete! Check dist/MBForge.exe")


if __name__ == "__main__":
    main()
