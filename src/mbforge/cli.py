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
    else:
        return _cmd_dev(args)  # 默认 dev 模式


def _cmd_dev(args) -> int:
    """开发模式：同时启动后端和前端，输出全部可见."""
    import os
    import subprocess
    import time

    if hasattr(args, "project") and args.project:
        os.environ["MBFORGE_OPEN_PROJECT"] = args.project

    setup_logging()

    # 找到项目根目录和前端目录
    project_root = Path(__file__).resolve().parent.parent.parent
    frontend_dir = project_root / "frontend"

    # 启动后端（输出直接打印到终端）
    print("\033[36m[后端]\033[0m 启动模型服务 (localhost:18792)...")
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "mbforge.model_server.main:app",
         "--host", "127.0.0.1", "--port", "18792"],
        cwd=str(project_root),
    )

    # 等后端就绪
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:18792/api/v1/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        print("\033[31m[后端]\033[0m 启动失败")
        backend.terminate()
        return 1

    print("\033[32m[后端]\033[0m 就绪")

    # 启动前端
    print("\033[36m[前端]\033[0m 启动 Vite 开发服务器 (localhost:5173)...")
    frontend = subprocess.Popen(
        ["npx", "vite"],
        cwd=str(frontend_dir),
    )

    print("\033[32m[前端]\033[0m 浏览器打开 http://localhost:5173")
    print("\033[90m按 Ctrl+C 停止所有服务\033[0m\n")

    try:
        # 等待任一进程退出
        while backend.poll() is None and frontend.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n\033[33m正在停止服务...\033[0m")
    finally:
        backend.terminate()
        frontend.terminate()

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
    setup_logging()
    from .core.project import Project
    from .core.knowledge_base import KnowledgeBase
    from .core.mol_database import MoleculeDatabase
    from .models import create_embedder_from_config, create_llm_from_config
    from .parsers.pdf_parser import PDFParserPipeline
    from .utils.config import load_global_config

    root = Path(args.path).resolve()
    project = Project.open(root)
    if project is None:
        logger.error(f"{root} 不是有效的 MBForge 项目")
        return 1

    config = load_global_config()
    embedder = create_embedder_from_config(config.embed)
    llm = create_llm_from_config(config.llm)
    kb = KnowledgeBase(project.root, embedder=embedder)
    mol_db = MoleculeDatabase(project.root)

    pipeline = PDFParserPipeline(
        llm=llm,
        embedder=embedder,
        knowledge_base=kb,
        mol_db=mol_db,
    )

    entries = project.scan_files()
    to_index = [e for e in entries if not e.indexed]
    logger.info(f"发现 {len(entries)} 个文件，待索引 {len(to_index)} 个")

    for entry in to_index:
        if entry.doc_type == "pdf":
            logger.info(f"索引: {entry.path.name}")
            try:
                pipeline.parse(entry.path, doc_id=entry.doc_id)
                entry.indexed = True
            except Exception as e:
                logger.error(f"索引失败: {entry.path.name} - {e}")

    logger.info("索引完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
