"""MBForge 图标规格校验 — 验证生成产物符合 Tauri/Android/iOS 平台要求。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
TAURI_ICONS = ROOT / "src-tauri" / "icons"

# Tauri 桌面必需文件清单 (path, expected_size)
TAURI_REQUIRED: list[tuple[str, int | None]] = [
    ("icon.png", 1024),
    ("32x32.png", 32),
    ("128x128.png", 128),
    ("128x128@2x.png", 256),
    ("icon.ico", None),
    ("icon.icns", None),
]

# Android 5 密度
ANDROID_DENSITIES: dict[str, int] = {
    "mdpi": 48,
    "hdpi": 72,
    "xhdpi": 96,
    "xxhdpi": 144,
    "xxxhdpi": 192,
}

# iOS AppIcon 尺寸
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


def test_tauri_icon_png_exists() -> None:
    """Tauri 必需 PNG 图标全部存在。"""
    for name, _ in TAURI_REQUIRED:
        if name.endswith(".png"):
            assert (TAURI_ICONS / name).exists(), f"Missing: {name}"


def test_tauri_icon_png_dimensions() -> None:
    """Tauri PNG 尺寸严格匹配。"""
    for name, expected_size in TAURI_REQUIRED:
        if name.endswith(".png") and expected_size is not None:
            img = Image.open(TAURI_ICONS / name)
            assert img.size == (expected_size, expected_size), (
                f"{name}: expected {expected_size}x{expected_size}, got {img.size}"
            )


def test_tauri_icon_ico_multiframe() -> None:
    """Tauri .ico 存在且包含多帧（通过 ICONDIR header 解析）。"""
    import struct

    ico_path = TAURI_ICONS / "icon.ico"
    assert ico_path.exists(), "icon.ico missing"
    with ico_path.open("rb") as f:
        reserved, type_, count = struct.unpack("<HHH", f.read(6))
    assert reserved == 0 and type_ == 1, "invalid ICO header"
    assert count >= 4, f"icon.ico should have multiple frames, got {count}"


def test_tauri_icon_icns_multiframe() -> None:
    """Tauri .icns 存在且包含多帧（验证 magic + 文件大小）。"""
    icns_path = TAURI_ICONS / "icon.icns"
    assert icns_path.exists(), "icon.icns missing"
    data = icns_path.read_bytes()
    assert data[:4] == b"icns", "invalid ICNS magic"
    # 7 帧 16~1024 多帧 ICNS 至少 50KB
    assert len(data) > 50_000, f"icon.icns suspiciously small: {len(data)} bytes"


def test_android_mipmaps_exist() -> None:
    """Android 5 密度 mipmap 全部存在。"""
    for dpi in ANDROID_DENSITIES:
        for variant in ("ic_launcher", "ic_launcher_round", "ic_launcher_foreground"):
            path = TAURI_ICONS / "android" / f"mipmap-{dpi}" / f"{variant}.png"
            assert path.exists(), f"Missing: {path.relative_to(ROOT)}"


def test_android_mipmap_dimensions() -> None:
    """Android mipmap 尺寸匹配密度。"""
    for dpi, size in ANDROID_DENSITIES.items():
        for variant in ("ic_launcher", "ic_launcher_round"):
            path = TAURI_ICONS / "android" / f"mipmap-{dpi}" / f"{variant}.png"
            img = Image.open(path)
            assert img.size == (size, size), (
                f"{path.name}: expected {size}x{size}, got {img.size}"
            )


def test_ios_appicons_exist() -> None:
    """iOS AppIcon 全尺寸存在。"""
    for name in IOS_SIZES:
        path = TAURI_ICONS / "ios" / name
        assert path.exists(), f"Missing: ios/{name}"


def test_ios_appicon_dimensions() -> None:
    """iOS AppIcon 尺寸匹配。"""
    for name, expected_size in IOS_SIZES.items():
        path = TAURI_ICONS / "ios" / name
        img = Image.open(path)
        assert img.size == (expected_size, expected_size), (
            f"{name}: expected {expected_size}x{expected_size}, got {img.size}"
        )


def test_master_png_anvil_is_solid() -> None:
    """主稿 PNG 铁砧剪影为实心黑色（采样关键点应全黑）。"""
    master = TAURI_ICONS / "icon.png"
    img = Image.open(master).convert("RGBA")
    px = img.load()
    # 铁砧剪影关键点（viewBox 1024，单 path 重绘后几何）
    # 顶面 x∈[353,613] y∈[400,460]; 腰 x∈[403,563] y∈[460,540]; 底座 x∈[251,715] y∈[540,630]
    samples = [
        (480, 430),  # 顶面中
        (480, 500),  # 腰中
        (480, 580),  # 底座中
        (700, 440),  # 角锥尖端附近
    ]
    for x, y in samples:
        r, g, b, _ = px[x, y]
        assert r < 50 and g < 50 and b < 50, (
            f"anvil pixel ({x},{y}) should be black, got ({r},{g},{b})"
        )


def test_master_png_bg_is_white() -> None:
    """主稿 PNG 背景为纯白（中心角区域，不在铁砧/六边形内）。"""
    master = TAURI_ICONS / "icon.png"
    img = Image.open(master).convert("RGBA")
    px = img.load()
    # 圆角内、安全区外：右上区域
    samples = [(512, 250), (250, 512), (770, 512), (512, 770)]
    for x, y in samples:
        r, g, b, _ = px[x, y]
        assert r > 200 and g > 200 and b > 200, (
            f"bg pixel ({x},{y}) should be white, got ({r},{g},{b})"
        )
