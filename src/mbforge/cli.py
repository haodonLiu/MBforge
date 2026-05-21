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

    # version
    parser.add_argument("--version", action="version", version="%(prog)s 0.2.0")

    args = parser.parse_args()

    if args.command == "init":
        return _cmd_init(args)
    elif args.command == "index":
        return _cmd_index(args)
    else:
        return _cmd_gui(args)


def _cmd_gui(args) -> int:
    from .app import run_app

    # 如果有 --project，先预加载
    extra = []
    if hasattr(args, "project") and args.project:
        # 通过环境变量传递，主窗口启动后读取
        import os
        os.environ["MBFORGE_OPEN_PROJECT"] = args.project

    return run_app(extra)


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
