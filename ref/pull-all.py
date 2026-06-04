#!/usr/bin/env python3
"""一键拉取/更新 ref/ 目录下的所有外部参考仓库。

用法:
    python ref/pull-all.py
    # 或从项目根目录:
    python -m ref.pull-all
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# (目录名, 远程仓库 URL)
REPOS: list[tuple[str, str]] = [
    ("GESim", "https://github.com/LazyShion/GESim.git"),
    ("chematic", "https://github.com/kent-tokyo/chematic.git"),
    ("paddleocr-vl-local", "https://github.com/CHEN010325/paddleocr-vl-local"),
    ("MoleCode", "https://github.com/AtomFlow-AI/MoleCode.git"),
]


def _run(cmd: list[str], cwd: Path | None = None) -> int:
    print(f"  > {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        for line in result.stdout.rstrip().splitlines():
            print(f"    {line}")
    if result.stderr:
        for line in result.stderr.rstrip().splitlines():
            print(f"    {line}", file=sys.stderr)
    return result.returncode


def main() -> None:
    base = Path(__file__).parent.resolve()
    print(f"Working directory: {base}\n")

    for name, url in REPOS:
        repo_path = base / name
        print(f"[{name}]")

        if (repo_path / ".git").exists():
            print(f"  Existing repo found at {repo_path}, pulling...")
            rc = _run(["git", "pull"], cwd=repo_path)
        else:
            print(f"  Cloning from {url}...")
            rc = _run(["git", "clone", url, str(repo_path)])

        if rc != 0:
            print(f"  ⚠️  Exit code {rc}\n")
        else:
            print(f"  ✅ OK\n")

    print("Done.")


if __name__ == "__main__":
    main()
