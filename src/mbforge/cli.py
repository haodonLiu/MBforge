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

    # gui 命令（默认）
    gui_parser = subparsers.add_parser("gui", help="启动图形界面（默认）")
    gui_parser.add_argument("--project", "-p", type=str, help="直接打开指定项目路径")

    # init 命令
    init_parser = subparsers.add_parser("init", help="初始化新项目")
    init_parser.add_argument("path", type=str, help="项目目录路径")
    init_parser.add_argument("--name", "-n", type=str, help="项目名称")

    # index 命令
    index_parser = subparsers.add_parser("index", help="索引项目文件")
    index_parser.add_argument("path", type=str, help="项目目录路径")

    # zotero-bridge 命令
    bridge_parser = subparsers.add_parser("zotero-bridge", help="启动 Zotero 桥接服务")
    bridge_parser.add_argument("--project", "-p", type=str, required=True, help="MBForge 项目目录路径")
    bridge_parser.add_argument("--host", type=str, default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    bridge_parser.add_argument("--port", type=int, default=8233, help="监听端口（默认 8233）")

    # version
    from .utils.constants import APP_VERSION

    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {APP_VERSION}"
    )

    args = parser.parse_args()

    if args.command == "init":
        return _cmd_init(args)
    elif args.command == "index":
        return _cmd_index(args)
    elif args.command == "zotero-bridge":
        return _cmd_zotero_bridge(args)
    else:
        return _cmd_gui(args)


def _cmd_gui(args) -> int:
    import os
    import subprocess
    import time
    import webbrowser

    # 如果有 --project，通过环境变量传递
    if hasattr(args, "project") and args.project:
        os.environ["MBFORGE_OPEN_PROJECT"] = args.project

    # 启动模型服务器
    setup_logging()
    logger.info("启动 MBForge 模型服务...")
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "mbforge.model_server.main:app",
         "--host", "127.0.0.1", "--port", "18792"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # 等待服务就绪
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:18792/api/v1/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        logger.error("模型服务启动失败")
        server_proc.terminate()
        return 1

    logger.info("模型服务已就绪，打开浏览器...")
    webbrowser.open("http://localhost:5173")

    try:
        server_proc.wait()
    except KeyboardInterrupt:
        logger.info("正在关闭模型服务...")
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


def _cmd_zotero_bridge(args) -> int:
    setup_logging()
    from .zotero_bridge.server import run_server

    project_root = Path(args.project).resolve()
    if not project_root.exists():
        logger.error("项目目录不存在: %s", project_root)
        return 1

    run_server(project_root=project_root, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
