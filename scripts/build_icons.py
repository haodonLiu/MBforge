"""MBForge 图标构建脚本 — 幂等，从 SVG 源生成全平台图标。

用法:
    uv run python scripts/build_icons.py

依赖 (项目内已通过 uv 装好):
    - cairosvg  (SVG → PNG)
    - Pillow 12+ (PNG resize / .ico / .icns / Android round)
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
TAURI_ICONS = ROOT / "src-tauri" / "icons"

# Tauri 桌面 PNG 列表 (filename, size)
TAURI_PNG_SIZES: list[tuple[str, int]] = [
    ("32x32.png", 32),
    ("128x128.png", 128),
    ("128x128@2x.png", 256),
    ("icon.png", 1024),
]

# Android 5 密度
ANDROID_DENSITIES: dict[str, int] = {
    "mdpi": 48,
    "hdpi": 72,
    "xhdpi": 96,
    "xxhdpi": 144,
    "xxxhdpi": 192,
}

# iOS AppIcon 全尺寸
IOS_SIZES: dict[str, int] = {
    "AppIcon-20x20@1x.png": 20,
    "AppIcon-20x20@2x-1.png": 40,
    "AppIcon-20x20@2x.png": 40,
    "AppIcon-20x20@3x.png": 60,
    "AppIcon-29x29@1x.png": 29,
    "AppIcon-29x29@2x-1.png": 58,
    "AppIcon-29x29@2x.png": 58,
    "AppIcon-29x29@3x.png": 87,
    "AppIcon-40x40@1x.png": 40,
    "AppIcon-40x40@2x-1.png": 80,
    "AppIcon-40x40@2x.png": 80,
    "AppIcon-40x40@3x.png": 120,
    "AppIcon-60x60@2x.png": 120,
    "AppIcon-60x60@3x.png": 180,
    "AppIcon-76x76@1x.png": 76,
    "AppIcon-76x76@2x.png": 152,
    "AppIcon-83.5x83.5@2x.png": 167,
    "AppIcon-512@2x.png": 1024,
}


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


def write_tauri_pngs(master: Image.Image) -> None:
    """生成 Tauri 桌面 PNG。"""
    TAURI_ICONS.mkdir(parents=True, exist_ok=True)
    for name, size in TAURI_PNG_SIZES:
        out = TAURI_ICONS / name
        master.resize((size, size), Image.LANCZOS).save(out, "PNG", optimize=True)
        print(f"[tauri]   {name} ({size}x{size})")


def write_ico(master: Image.Image) -> None:
    """生成 .ico 多帧 (16/32/48/64/128/256)。"""
    out = TAURI_ICONS / "icon.ico"
    sizes = [16, 32, 48, 64, 128, 256]
    # Pillow ICO 插件：通过 sizes 参数生成多帧（单源图即可）
    master.save(out, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"[tauri]   icon.ico ({len(sizes)} frames)")


def write_icns(master: Image.Image) -> None:
    """生成 .icns 多帧 (Pillow 内置 ICNS 插件)。"""
    out = TAURI_ICONS / "icon.icns"
    # ICNS 尺寸必须按升序排列；Pillow 按尺寸自动选 ic07/ic08/ic09 类型
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    master.save(out, format="ICNS", sizes=[(s, s) for s in sizes])
    print(f"[tauri]   icon.icns ({len(sizes)} frames)")


def write_android(master: Image.Image) -> None:
    """生成 Android 5 密度 mipmap。"""
    for dpi, size in ANDROID_DENSITIES.items():
        d = TAURI_ICONS / "android" / f"mipmap-{dpi}"
        d.mkdir(parents=True, exist_ok=True)
        mip = master.resize((size, size), Image.LANCZOS)
        mip.save(d / "ic_launcher.png", "PNG", optimize=True)
        mip.save(d / "ic_launcher_round.png", "PNG", optimize=True)
        # Foreground: 内容留 18% 边距（系统自适应遮罩）
        fg_size = int(size * 0.82)
        pad = (size - fg_size) // 2
        fg = master.resize((fg_size, fg_size), Image.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(fg, (pad, pad), fg)
        canvas.save(d / "ic_launcher_foreground.png", "PNG", optimize=True)
        print(f"[android] mipmap-{dpi} ({size}px)")


def write_ios(master: Image.Image) -> None:
    """生成 iOS AppIcon 全尺寸。"""
    d = TAURI_ICONS / "ios"
    d.mkdir(parents=True, exist_ok=True)
    for name, size in IOS_SIZES.items():
        master.resize((size, size), Image.LANCZOS).save(d / name, "PNG", optimize=True)
    print(f"[ios]     {len(IOS_SIZES)} AppIcon sizes written")


def main() -> None:
    print(f"Building MBForge icons from {SVG.relative_to(ROOT)}")
    master = render_master()
    write_tauri_pngs(master)
    write_ico(master)
    write_icns(master)
    write_android(master)
    write_ios(master)
    print("Done.")


if __name__ == "__main__":
    main()
