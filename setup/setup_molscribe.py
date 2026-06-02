#!/usr/bin/env python3
"""MolScribe 环境搭建脚本 — 一键安装依赖 + 下载模型.

用法:
    python setup/setup_molscribe.py

会安装:
    1. timm (MolScribe 专用版本，不是 PyPI 最新版)
    2. OpenNMT-py
    3. 下载 MolScribe checkpoint (~1 GB)
    4. 下载 MolDet checkpoint (~25 MB)
"""

import subprocess
import sys
from pathlib import Path

# MolScribe 仓库指定的 timm commit
TIMM_GIT_URL = "git+https://github.com/rwightman/pytorch-image-models.git@54a6cca27a9a3e092a07457f5d56709da56e3cf5"
ONMT_VERSION = "OpenNMT-py==2.2.0"

# 模型下载
MODELS = {
    "moldetv2-doc": {
        "url": "https://huggingface.co/yujieq/MolDetect/resolve/main/best.pt",
        "filename": "moldetv2-doc.pt",
        "size_mb": 25,
    },
    "moldetv2-general": {
        "url": "https://huggingface.co/yujieq/MolDetect/resolve/main/best.pt",
        "filename": "moldetv2-general.pt",
        "size_mb": 25,
    },
    "molscribe": {
        "url": "https://huggingface.co/yujieq/MolScribe/resolve/main/swin_base_char_aux_1m680k.pth",
        "filename": "MolScribe/swin_base_char_aux_1m680k.pth",
        "size_mb": 1082,
    },
}


def run(cmd: list[str], desc: str) -> bool:
    print(f"\n{'='*60}")
    print(f"  {desc}")
    print(f"  $ {' '.join(cmd)}")
    print(f"{'='*60}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n  ✗ 失败: {desc}")
        return False
    print(f"\n  ✓ 完成: {desc}")
    return True


def get_model_cache_dir() -> Path:
    """获取模型缓存目录."""
    try:
        from mbforge.utils.constants import get_model_cache_dir
        return Path(get_model_cache_dir())
    except ImportError:
        return Path.home() / ".cache" / "mbforge" / "models"


def download_file(url: str, dest: Path, desc: str) -> bool:
    """下载文件并显示进度."""
    if dest.exists():
        print(f"  ✓ 已存在: {dest.name}")
        return True

    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"\n  下载 {desc}...")
    print(f"  → {dest}")

    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "MBForge/1.0"})
        with urllib.request.urlopen(req, timeout=600) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(262144)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = downloaded * 100 // total
                        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                        print(f"\r  [{bar}] {pct}% ({downloaded // 1024 // 1024}MB/{total // 1024 // 1024}MB)", end="", flush=True)
            print()
        print(f"  ✓ 完成: {dest.name}")
        return True
    except Exception as e:
        print(f"\n  ✗ 下载失败: {e}")
        if dest.exists():
            dest.unlink()
        return False


def main():
    print("""
╔══════════════════════════════════════════════════╗
║        MBForge MolScribe 环境搭建脚本            ║
╚══════════════════════════════════════════════════╝
""")

    # Step 1: 安装 timm (MolScribe 专用版本)
    # 先检查是否已有正确版本
    try:
        import timm
        if hasattr(timm, '__version__') and timm.__version__ == '0.4.11':
            print("  ✓ timm 0.4.11 已安装")
        else:
            print(f"  ⚠ timm {timm.__version__} 已安装，但 MolScribe 需要 0.4.11")
            run([sys.executable, "-m", "pip", "install", TIMM_GIT_URL], "安装 timm (MolScribe 专用版本)")
    except ImportError:
        run([sys.executable, "-m", "pip", "install", TIMM_GIT_URL], "安装 timm (MolScribe 专用版本)")

    # Step 2: 安装 OpenNMT-py
    try:
        import onmt
        print(f"  ✓ OpenNMT-py 已安装")
    except ImportError:
        run([sys.executable, "-m", "pip", "install", ONMT_VERSION], "安装 OpenNMT-py")

    # Step 3: 安装 timm (确保正确版本)
    # timm 需要从 MolScribe 指定的 git commit 安装
    # 先检查当前 timm 版本

    # Step 4: 下载模型
    cache_dir = get_model_cache_dir()
    print(f"\n模型缓存目录: {cache_dir}")

    for model_id, info in MODELS.items():
        dest = cache_dir / info["filename"]
        download_file(info["url"], dest, f"{model_id} (~{info['size_mb']} MB)")

    # Step 5: 验证
    print(f"\n{'='*60}")
    print("  验证安装")
    print(f"{'='*60}\n")

    checks = [
        ("timm", "import timm"),
        ("onmt", "import onmt"),
        ("torch+CUDA", "import torch; assert torch.cuda.is_available()"),
        ("ultralytics", "import ultralytics"),
        ("MolScribe 模型", f"from pathlib import Path; assert Path('{cache_dir}/MolScribe/swin_base_char_aux_1m680k.pth').exists()"),
        ("MolDet 模型", f"from pathlib import Path; assert Path('{cache_dir}/moldetv2-doc.pt').exists()"),
    ]

    all_ok = True
    for name, code in checks:
        try:
            exec(code)
            print(f"  ✓ {name}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            all_ok = False

    print()
    if all_ok:
        print("  ╔══════════════════════════════════════╗")
        print("  ║  ✓ 全部验证通过！管线可以运行。       ║")
        print("  ╚══════════════════════════════════════╝")
    else:
        print("  ⚠ 部分验证失败，请检查上方错误信息。")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
