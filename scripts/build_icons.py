"""MBForge 图标构建脚本 — 幂等，从 SVG 源生成 master PNG。

用法:
    uv run python scripts/build_icons.py

依赖 (项目内已通过 uv 装好):
    - cairosvg  (SVG → PNG)
    - Pillow    (load + save)
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import cairosvg
from PIL import Image

# ---- 路径配置 ----
ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / "assets" / "icon" / "icon.svg"
MASTER_PNG = ROOT / "assets" / "icon" / "icon-master.png"


def render_master() -> Image.Image:
    """SVG → 1024×1024 RGBA 主稿。"""
    if not SVG.exists():
        sys.exit(f"ERROR: SVG source not found: {SVG}")
    png_bytes = cairosvg.svg2png(url=str(SVG), output_width=1024, output_height=1024)
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    MASTER_PNG.parent.mkdir(parents=True, exist_ok=True)
    img.save(MASTER_PNG, "PNG", optimize=True)
    print(f"[master] {MASTER_PNG.relative_to(ROOT)} ({img.size[0]}x{img.size[1]})")
    return img


def main() -> None:
    print(f"Building MBForge icons from {SVG.relative_to(ROOT)}")
    render_master()
    print("Done.")


if __name__ == "__main__":
    main()
