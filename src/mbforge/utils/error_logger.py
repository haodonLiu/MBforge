"""报错记录工具.

将运行时错误记录到 docs/errors/ 目录，包含索引和详情文件。
"""

from __future__ import annotations

import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

from .logger import get_logger

logger = get_logger(__name__)

# 项目根目录下的 docs/errors/，不存在则 fallback 到用户目录
_ERRORS_DIR = Path(__file__).resolve().parents[3] / "docs" / "errors"
if not _ERRORS_DIR.parent.exists():
    _ERRORS_DIR = Path.home() / ".local" / "share" / "MBForge" / "errors"


def record_error(
    module: str,
    summary: str,
    error: Optional[Exception] = None,
    solution: str = "",
    status: str = "待解决",
) -> Path:
    """记录一个错误到 docs/errors/ 目录.

    Args:
        module: 出错模块路径（如 "agent/anthropic_llm"）
        summary: 错误摘要（一句话）
        error: 异常对象（可选，用于记录堆栈）
        solution: 解决方案（可选，后续补充）
        status: 状态（待解决 / 已解决）

    Returns:
        详情文件路径
    """
    _ERRORS_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")

    # 找到下一个编号
    existing = list(_ERRORS_DIR.glob(f"{date_str}-*.md"))
    next_num = len(existing) + 1
    num_str = f"{next_num:03d}"

    filename = f"{date_str}-{num_str}.md"
    detail_path = _ERRORS_DIR / filename

    # 构建详情内容
    lines = [
        f"# {num_str}: {summary}",
        "",
        f"**日期：** {date_str}",
        f"**模块：** `{module}`",
        f"**状态：** {status}",
        "",
        "## 错误描述",
        "",
    ]

    if error:
        lines.append(f"```")
        lines.append(f"{type(error).__name__}: {error}")
        lines.append(f"```")
        lines.append("")
        lines.append("## 堆栈")
        lines.append("")
        lines.append("```")
        lines.append(traceback.format_exc())
        lines.append("```")
    else:
        lines.append(summary)
        lines.append("")

    if solution:
        lines.extend(["## 解决方案", "", solution, ""])

    # 写入详情文件
    detail_path.write_text("\n".join(lines), encoding="utf-8")

    # 更新索引
    _update_index(date_str, num_str, module, summary, status)

    logger.info(f"Error recorded: {filename}")
    return detail_path


def _update_index(
    date_str: str,
    num_str: str,
    module: str,
    summary: str,
    status: str,
) -> None:
    """更新 errors/README.md 索引."""
    index_path = _ERRORS_DIR / "README.md"
    if not index_path.exists():
        index_path.write_text(
            "# 报错记录索引\n\n按时间倒序排列。每个错误的详细分析见对应编号文件。\n\n"
            "| 日期 | 编号 | 模块 | 错误摘要 | 状态 |\n"
            "|------|------|------|----------|------|\n",
            encoding="utf-8",
        )

    content = index_path.read_text(encoding="utf-8")
    new_row = f"| {date_str} | {num_str} | {module} | {summary} | {status} |"

    # 插入到表头之后（第二行之后）
    lines = content.split("\n")
    header_end = 0
    for i, line in enumerate(lines):
        if line.startswith("|------"):
            header_end = i + 1
            break

    lines.insert(header_end, new_row)
    index_path.write_text("\n".join(lines), encoding="utf-8")
