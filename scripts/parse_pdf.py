"""PDF 解析脚本 — 使用 parsers.uniparser 模块调用 UniParser 解析 PDF 文件.

用法:
    python parse_pdf.py <pdf文件路径> [--output <输出目录>] [--timeout <秒>]

依赖:
    - uniparser-tools SDK（需安装）
    - python-dotenv（可选，用于加载 .env）

环境变量 (或 .env 文件):
    UNIPARSER_HOST    例如 https://your-server.com
    UNIPARSER_API_KEY 你的 API 密钥
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# 确保可以找到 src/ 下的模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mbforge.parsers.uniparser import ParserClient, ParserConfig, ParseResult


def load_config() -> ParserConfig:
    """从环境变量加载 UniParser 配置."""
    import os
    return ParserConfig(
        host=os.getenv("UNIPARSER_HOST", ""),
        api_key=os.getenv("UNIPARSER_API_KEY", ""),
    )


def parse_pdf(
    pdf_path: str,
    output_dir: str | None = None,
    timeout: int = 300,
) -> ParseResult:
    """解析 PDF 文件，等待完成后返回结果。"""
    pdf = Path(pdf_path).resolve()
    if not pdf.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {pdf}")

    # 加载配置（来自 .env 或环境变量）
    config = load_config()
    client = ParserClient(config)

    print(f"📄 开始解析: {pdf.name}")
    print(f"🔗 服务端: {config.host}")

    # 发出异步解析请求，获取 token
    result = client.parse_pdf(str(pdf), sync=False)

    if not result.token:
        raise RuntimeError(f"解析失败: {result.status}")

    print(f"🆔 Token: {result.token}")
    print("⏳ 等待解析完成...")

    # 轮询等待完成
    elapsed = 0
    poll_interval = 2
    while elapsed < timeout:
        resp = client.get_result(token=result.token, content=True)
        status = resp.get("status", "")
        progress = resp.get("progress", 0)

        if status == "completed":
            result.raw_data = resp
            print("✅ 解析完成！")
            break

        if status == "failed":
            error = resp.get("error", "未知错误")
            raise RuntimeError(f"解析失败: {error}")

        # 简单进度显示
        bar_len = 30
        filled = int(bar_len * progress / 100) if progress else 0
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r   [{bar}] {progress:.0f}%", end="", flush=True)

        time.sleep(poll_interval)
        elapsed += poll_interval
    else:
        raise TimeoutError(f"解析超时（{timeout} 秒）")

    return result


def save_results(result: ParseResult, output_dir: str, pdf_name: str) -> dict:
    """保存解析结果为 JSON 和纯文本文件。"""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    raw_data = result.raw_data
    stem = Path(pdf_name).stem

    # 1. 保存完整 JSON
    json_path = out / f"{stem}_result.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)
    print(f"📝 JSON: {json_path}")

    # 2. 提取并保存纯文本内容
    content = raw_data.get("content", "")
    if content:
        txt_path = out / f"{stem}_content.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"📝 文本: {txt_path}")

    # 3. 保存摘要信息
    summary = {
        "token": result.token,
        "status": result.status,
        "pages": raw_data.get("pages", 0),
        "md5": raw_data.get("md5", ""),
        "char_count": len(content) if content else 0,
    }
    summary_path = out / f"{stem}_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"📋 摘要: {summary_path}")

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="使用 UniParser 解析 PDF 文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("pdf", help="要解析的 PDF 文件路径")
    parser.add_argument(
        "-o", "--output",
        default="output",
        help="输出目录（默认: output/）",
    )
    parser.add_argument(
        "-t", "--timeout",
        type=int,
        default=300,
        help="等待超时秒数（默认: 300）",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="不保存文件，仅打印结果",
    )

    args = parser.parse_args()

    try:
        result = parse_pdf(args.pdf, timeout=args.timeout)
    except (FileNotFoundError, RuntimeError, TimeoutError) as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    if args.no_save:
        print("\n--- 原始返回数据 ---")
        print(json.dumps(result.raw_data, ensure_ascii=False, indent=2))
        return

    summary = save_results(result, args.output, args.pdf)
    print(f"\n📊 共 {summary['char_count']} 字符")
    print("✅ 解析完成！")


if __name__ == "__main__":
    main()
