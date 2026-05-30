"""MBForge 命令行入口."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 优先加载项目根目录的 .env 文件
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from .utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


def main() -> int:
    """CLI 主入口."""
    parser = argparse.ArgumentParser(
        prog="mbforge",
        description="MBForge - Molecular Knowledge Base & AI Workbench",
    )
    subparsers = parser.add_subparsers(dest="command")

    # dev 命令（推荐）— 同时启动前后端，输出可见
    dev_parser = subparsers.add_parser("dev", help="开发模式：同时启动前后端")
    dev_parser.add_argument("--project", "-p", type=str, help="直接打开指定项目路径")

    # gui 命令 — 仅启动后端 + 打开浏览器
    gui_parser = subparsers.add_parser("gui", help="启动后端并打开浏览器")
    gui_parser.add_argument("--project", "-p", type=str, help="直接打开指定项目路径")

    # init 命令
    init_parser = subparsers.add_parser("init", help="初始化新项目")
    init_parser.add_argument("path", type=str, help="项目目录路径")
    init_parser.add_argument("--name", "-n", type=str, help="项目名称")

    # index 命令
    index_parser = subparsers.add_parser("index", help="索引项目文件")
    index_parser.add_argument("path", type=str, help="项目目录路径")

    # download 命令 — 下载可选模型
    dl_parser = subparsers.add_parser("download", help="下载可选模型（MolDetv2/MolScribe）")
    dl_parser.add_argument("model", nargs="?", default="all",
                           choices=["all", "moldet", "molscribe"],
                           help="要下载的模型（默认 all）")

    # version
    from .utils.constants import APP_VERSION

    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {APP_VERSION}"
    )

    args = parser.parse_args()

    if args.command == "dev":
        return _cmd_dev(args)
    elif args.command == "gui":
        return _cmd_gui(args)
    elif args.command == "init":
        return _cmd_init(args)
    elif args.command == "index":
        return _cmd_index(args)
    elif args.command == "download":
        return _cmd_download(args)
    else:
        return _cmd_dev(args)  # 默认 dev 模式


def _cmd_dev(args) -> int:
    """开发模式：后端和前端分别在独立终端窗口中启动."""
    import os
    import subprocess
    import time

    if hasattr(args, "project") and args.project:
        os.environ["MBFORGE_OPEN_PROJECT"] = args.project

    setup_logging()

    project_root = Path(__file__).resolve().parent.parent.parent
    frontend_dir = project_root / "frontend"

    is_windows = sys.platform == "win32"

    if is_windows:
        import shutil
        import tempfile

        npx_cmd = shutil.which("npx") or "npx"

        # 写临时 .bat 文件避免路径空格截断问题
        backend_bat = tempfile.NamedTemporaryFile(
            mode="w", suffix=".bat", delete=False, prefix="mbforge_backend_",
            dir=str(Path(os.environ.get("TEMP", "C:\\Windows\\Temp"))),
        )
        backend_bat.write(f'@echo off\ncd /d "{project_root}"\n"{sys.executable}" -m uvicorn mbforge.model_server.main:app --host 127.0.0.1 --port 18792\npause\n')
        backend_bat.close()

        frontend_bat = tempfile.NamedTemporaryFile(
            mode="w", suffix=".bat", delete=False, prefix="mbforge_frontend_",
            dir=str(Path(os.environ.get("TEMP", "C:\\Windows\\Temp"))),
        )
        frontend_bat.write(f'@echo off\ncd /d "{frontend_dir}"\n"{npx_cmd}" vite\npause\n')
        frontend_bat.close()

        # start 的第一个带引号参数被视为窗口标题，所以用双引号包 bat 路径即可
        subprocess.Popen(
            f'start "MBForge 后端 (localhost:18792)" cmd /k "{backend_bat.name}"',
            shell=True,
        )
        subprocess.Popen(
            f'start "MBForge 前端 (localhost:5173)" cmd /k "{frontend_bat.name}"',
            shell=True,
        )
    else:
        import shutil
        npx_cmd = shutil.which("npx") or "npx"
        backend_cmd = f'cd "{project_root}" && {sys.executable} -m uvicorn mbforge.model_server.main:app --host 127.0.0.1 --port 18792; exec bash'
        frontend_cmd = f'cd "{frontend_dir}" && {npx_cmd} vite; exec bash'
        for title, cmd in [("MBForge 后端", backend_cmd), ("MBForge 前端", frontend_cmd)]:
            for term in ["wt", "gnome-terminal", "xterm", "konsole"]:
                if shutil.which(term):
                    subprocess.Popen([term, "--title", title, "-e", "bash", "-c", cmd])
                    break

    print("\033[32m[后端]\033[0m 已在新终端窗口启动 (localhost:18792)")
    print("\033[32m[前端]\033[0m 已在新终端窗口启动 (localhost:5173)")
    print("\033[90m关闭对应终端窗口即可停止各服务\033[0m")

    # 等后端就绪后打开浏览器
    import urllib.request
    print("\033[90m等待后端就绪...\033[0m")
    for i in range(60):
        try:
            urllib.request.urlopen("http://127.0.0.1:18792/api/v1/health", timeout=2)
            break
        except Exception:
            time.sleep(1)
    else:
        print("\033[31m[后端]\033[0m 等待超时，请检查后端终端窗口")
        return 1

    print("\033[32m[后端]\033[0m 就绪")
    print("\033[32m[前端]\033[0m 浏览器打开 http://localhost:5173\n")
    import webbrowser
    webbrowser.open("http://localhost:5173")

    return 0


def _cmd_gui(args) -> int:
    """仅启动后端 + 打开浏览器（不启动前端 dev server）."""
    import os
    import subprocess
    import time
    import webbrowser

    if hasattr(args, "project") and args.project:
        os.environ["MBFORGE_OPEN_PROJECT"] = args.project

    setup_logging()
    print("\033[36m[后端]\033[0m 启动模型服务 (localhost:18792)...")
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "mbforge.model_server.main:app",
         "--host", "127.0.0.1", "--port", "18792"],
    )

    import urllib.request
    for _ in range(30):
        if server_proc.poll() is not None:
            print(f"\033[31m[后端]\033[0m 进程异常退出 (code={server_proc.returncode})，可能端口已被占用")
            return 1
        try:
            urllib.request.urlopen("http://127.0.0.1:18792/api/v1/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        print("\033[31m[后端]\033[0m 启动失败")
        server_proc.terminate()
        return 1

    print("\033[32m[后端]\033[0m 就绪，打开浏览器...")
    webbrowser.open("http://localhost:5173")

    try:
        server_proc.wait()
    except KeyboardInterrupt:
        print("\n\033[33m正在停止服务...\033[0m")
        server_proc.terminate()
    return 0


def _cmd_init(args) -> int:
    setup_logging()
    from .core.project import Project

    root = Path(args.path).resolve()
    name = args.name or root.name
    project = Project.create(root, name=name)
    logger.info(f"项目已创建: {project.root}")
    logger.info(f"名称: {project.name}")
    return 0


def _cmd_index(args) -> int:
    """索引命令 — 已迁移到 Rust Tauri pipeline.

    使用前端的"索引项目"按钮，或通过 Tauri command 调用。
    """
    print("PDF 索引已迁移到 Rust pipeline。")
    print("请使用前端的'索引项目'按钮，或通过 Tauri command 调用。")
    return 0


# ---- 模型下载 ----

# MolDetv2 模型来自 Hugging Face
_MOLDET_MODELS = {
    "moldetv2-doc": {
        "repo": "yujieq/MolDetect",
        "filename": "best.pt",
        "local_name": "moldetv2-doc.pt",
        "desc": "MolDetv2-Doc 整页分子检测",
    },
    "moldetv2-general": {
        "repo": "yujieq/MolDetect",
        "filename": "best.pt",
        "local_name": "moldetv2-general.pt",
        "desc": "MolDetv2-General 裁剪区域检测",
    },
}

_MOLSCRIBE_MODELS = {
    "molscribe": {
        "repo": "yujieq/MolScribe",
        "filename": None,  # 使用 huggingface_hub 整包下载
        "local_name": "molscribe",
        "desc": "MolScribe SMILES 识别",
    },
}


def _download_with_progress(url: str, dest: Path) -> bool:
    """下载文件并显示进度条."""
    import urllib.request

    try:
        print(f"  下载: {dest.name}")
        req = urllib.request.Request(url, headers={"User-Agent": "MBForge/1.0"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 1024 * 256  # 256KB
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = downloaded * 100 // total
                        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                        print(f"\r  [{bar}] {pct}% ({downloaded // 1024}KB/{total // 1024}KB)", end="", flush=True)
                    else:
                        print(f"\r  已下载 {downloaded // 1024}KB", end="", flush=True)
            print()
        return True
    except Exception as e:
        print(f"\n  下载失败: {e}")
        if dest.exists():
            dest.unlink()
        return False


def _cmd_download(args) -> int:
    """下载可选模型."""
    setup_logging()
    model_choice = args.model

    target_dir = Path.home() / ".cache" / "mbforge" / "models"
    target_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped = 0
    failed = 0

    # 下载 MolDetv2 模型
    if model_choice in ("all", "moldet"):
        for name, info in _MOLDET_MODELS.items():
            dest = target_dir / name / info["local_name"]
            if dest.exists():
                print(f"\033[32m✓\033[0m {info['desc']} — 已存在")
                skipped += 1
                continue

            print(f"\n\033[36m下载 {info['desc']}...\033[0m")
            dest.parent.mkdir(parents=True, exist_ok=True)

            # 通过 Hugging Face API 获取下载链接
            url = f"https://huggingface.co/{info['repo']}/resolve/main/{info['filename']}"
            if _download_with_progress(url, dest):
                print(f"\033[32m✓\033[0m 下载完成: {dest}")
                downloaded += 1
            else:
                failed += 1
                print(f"  提示: 你也可以手动下载模型放到 {dest.parent}")

    # 下载 MolScribe 模型
    if model_choice in ("all", "molscribe"):
        for name, info in _MOLSCRIBE_MODELS.items():
            dest_dir = target_dir / info["local_name"]
            if dest_dir.exists() and any(dest_dir.glob("*.pt")):
                print(f"\033[32m✓\033[0m {info['desc']} — 已存在")
                skipped += 1
                continue

            print(f"\n\033[36m下载 {info['desc']}...\033[0m")
            dest_dir.mkdir(parents=True, exist_ok=True)

            # 使用 huggingface_hub（如果可用）
            try:
                from huggingface_hub import snapshot_download
                print("  使用 huggingface_hub 下载...")
                snapshot_download(
                    repo_id=info["repo"],
                    local_dir=str(dest_dir),
                )
                print(f"\033[32m✓\033[0m 下载完成: {dest_dir}")
                downloaded += 1
            except ImportError:
                print("  huggingface_hub 未安装，跳过 MolScribe")
                print("  安装: pip install huggingface_hub")
                failed += 1
            except Exception as e:
                print(f"  下载失败: {e}")
                failed += 1

    # 汇总
    print(f"\n{'='*40}")
    print(f"下载: {downloaded}  已有: {skipped}  失败: {failed}")
    if downloaded > 0:
        print(f"模型目录: {target_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
