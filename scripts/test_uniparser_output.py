"""UniParser 输出格式探索脚本.

用法:
    .venv/Scripts/python scripts/test_uniparser_output.py <pdf_path|local> [output_dir]

示例:
    .venv/Scripts/python scripts/test_uniparser_output.py local
    .venv/Scripts/python scripts/test_uniparser_output.py \
        "C:/Users/10954/Desktop/提取自MRGPRX2抑制剂及其使用方法.pdf"
"""

from __future__ import annotations

import json
import sys
import textwrap
from collections import Counter
from pathlib import Path
from typing import Any


def analyze_result(data: Any, title: str = "Result") -> str:
    """分析 UniParser 返回结果的结构并生成报告."""
    lines = [f"=== {title} ===", ""]

    if isinstance(data, list):
        lines.append(f"根类型: list，共 {len(data)} 页")
        lines.append("")
        type_counter: Counter = Counter()
        all_keys: set[str] = set()
        type_samples: dict[str, dict[str, Any]] = {}

        for page_idx, page in enumerate(data):
            if not isinstance(page, list):
                lines.append(f"  第 {page_idx} 项不是 list，而是 {type(page).__name__}")
                continue
            for item in page:
                if not isinstance(item, dict):
                    continue
                t = item.get("type", "unknown")
                type_counter[t] += 1
                all_keys.update(item.keys())
                if t not in type_samples:
                    type_samples[t] = item

        lines.append("--- 类型分布 ---")
        for t, c in type_counter.most_common():
            lines.append(f"  {t}: {c}")
        lines.append("")

        # 特别关注科学对象
        sci_types = {"molecule", "table", "equation", "expression", "chart", "figure", "image"}
        found_sci = [t for t in type_counter if t in sci_types or any(s in t for s in sci_types)]
        if found_sci:
            lines.append("--- 科学对象类型 ---")
            for t in found_sci:
                lines.append(f"  {t}: {type_counter[t]}")
            lines.append("")
        else:
            lines.append("--- 科学对象类型 ---")
            lines.append("  未检测到 molecule / table / equation / expression / chart / figure 等类型")
            lines.append("  可能原因：1) 文档本身不含此类对象 2) 解析时未启用对应模式")
            lines.append("")

        lines.append("--- 所有出现过的字段 ---")
        for k in sorted(all_keys):
            lines.append(f"  {k}")
        lines.append("")

        lines.append("--- 每种类型的字段与样例 ---")
        for t in sorted(type_samples.keys()):
            item = type_samples[t]
            lines.append(f"\n[{t}]")
            lines.append(f"  keys: {sorted(item.keys())}")
            for k in ("text", "contents", "items", "source", "level", "method", "smi", "caption", "desc"):
                if k in item:
                    v = item[k]
                    preview = str(v)[:300].replace("\n", "\\n")
                    lines.append(f"  {k}: {preview}")
        lines.append("")

    elif isinstance(data, dict):
        lines.append(f"根类型: dict，keys={list(data.keys())}")
        for k, v in data.items():
            if isinstance(v, str) and len(v) > 200:
                lines.append(f"  {k}: str[len={len(v)}] preview={v[:200]}...")
            elif isinstance(v, list):
                lines.append(f"  {k}: list[len={len(v)}]")
            else:
                lines.append(f"  {k}: {type(v).__name__}")
    else:
        lines.append(f"根类型: {type(data).__name__}")
        lines.append(str(data)[:500])

    return "\n".join(lines)


def save_analysis(data: Any, output_dir: Path, basename: str) -> None:
    """保存原始 JSON 和分析报告."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_path = output_dir / f"{basename}_raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[saved] 原始结果 -> {raw_path}")

    report = analyze_result(data, title=f"Analysis for {basename}")
    report_path = output_dir / f"{basename}_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[saved] 分析报告 -> {report_path}")

    print()
    print(report)


def test_with_live_service(pdf_path: Path, output_dir: Path) -> None:
    """使用真实 UniParser 服务解析 PDF."""
    try:
        from mbforge.parser_io import ParserClient, load_config
    except ImportError as e:
        print(f"导入失败: {e}")
        print("请确保在 .venv 环境中运行: .venv/Scripts/python scripts/test_uniparser_output.py ...")
        sys.exit(1)

    try:
        config = load_config()
    except ValueError as e:
        print(f"配置加载失败: {e}")
        print(textwrap.dedent("""\
            请检查 .env 文件中是否配置了真实的 UniParser 服务地址:

                UNIPARSER_HOST=https://uniparser.dp.tech
                UNIPARSER_API_KEY=your-api-key
        """))
        sys.exit(1)

    print(f"UniParser Host: {config.host}")
    print(f"解析文件: {pdf_path.resolve()}")
    print(f"文件大小: {pdf_path.stat().st_size / 1024:.1f} KB")
    print()

    client = ParserClient(config)

    # 先检查服务健康
    health = client.health()
    print(f"服务健康: {health}")
    print()

    # 科学文献推荐配置，启用所有对象识别
    print("发送解析请求（molecule/table/equation/figure 全启用，sync=false 异步模式）...")
    result = client.parse_pdf(
        pdf_path,
        sync=False,
        textual=2,      # OCRHighQuality
        table=2,        # OCRHighQuality
        equation=2,     # OCRHighQuality
        chart=-1,       # DumpBase64
        figure=-1,      # DumpBase64
        expression=-1,  # DumpBase64
        molecule=1,     # OCRFast
    )

    print(f"任务提交: status={result.status}, token={result.token}")

    # 轮询等待完成
    import time
    print("轮询等待解析完成...")
    timeout = 600
    poll_interval = 5
    elapsed = 0
    final_response = None
    while elapsed < timeout:
        response = client.get_result(token=result.token, content=True)
        status = response.get("status", "unknown")
        if status == "completed":
            final_response = response
            print(f"解析完成！耗时约 {elapsed} 秒")
            break
        elif status in ("error", "failed"):
            print(f"解析失败: {response}")
            sys.exit(1)
        else:
            print(f"  [{elapsed}s] status={status}, 继续等待...")
        time.sleep(poll_interval)
        elapsed += poll_interval
    else:
        print(f"解析超时（>{timeout}秒）")
        sys.exit(1)

    basename = Path(pdf_path).stem
    save_analysis(final_response, output_dir, basename)

    # 额外获取 Markdown 格式化结果
    print("\n获取 Markdown 格式化结果...")
    formatted = client.get_formatted(
        result.token,
        content=True,
        textual=4,   # Markdown
        table=4,
        equation=4,
        molecule=4,
    )
    fmt_path = output_dir / f"{basename}_formatted.json"
    with open(fmt_path, "w", encoding="utf-8") as f:
        json.dump(formatted, f, ensure_ascii=False, indent=2)
    print(f"[saved] 格式化结果 -> {fmt_path}")

    if isinstance(formatted, dict) and "content" in formatted:
        content = formatted["content"]
        md_path = output_dir / f"{basename}_formatted.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[saved] Markdown 全文 -> {md_path} (长度: {len(content)} 字符)")


def test_with_local_sample(output_dir: Path) -> None:
    """使用本地已有的 JSON 样本做离线结构分析."""
    sample_path = Path("UniParser-Tools/playground/results/aeb129da-4a36-4627-9cb2-c721def237f0.json")
    if not sample_path.exists():
        print(f"本地样本不存在: {sample_path}")
        return

    print(f"使用本地样本: {sample_path}")
    data = json.loads(sample_path.read_text("utf-8"))
    save_analysis(data, output_dir, "local_sample")


def main() -> None:
    if len(sys.argv) < 2:
        # 默认使用用户指定的 PDF
        default_pdf = Path("C:/Users/10954/Desktop/提取自MRGPRX2抑制剂及其使用方法.pdf")
        if default_pdf.exists():
            print(f"未指定参数，使用默认 PDF: {default_pdf}")
            test_with_live_service(default_pdf, Path("output/uniparser_test"))
            return
        print(textwrap.dedent("""\
            用法: .venv/Scripts/python scripts/test_uniparser_output.py <pdf_path|local> [output_dir]

            模式:
              local        - 分析本地已有的 JSON 样本（无需服务）
              <pdf_path>   - 连接真实 UniParser 服务解析指定 PDF

            示例:
              .venv/Scripts/python scripts/test_uniparser_output.py local
              .venv/Scripts/python scripts/test_uniparser_output.py \
                  "C:/Users/10954/Desktop/提取自MRGPRX2抑制剂及其使用方法.pdf"
        """))
        sys.exit(1)

    arg1 = sys.argv[1]
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("output/uniparser_test")

    if arg1.lower() == "local":
        test_with_local_sample(output_dir)
    else:
        pdf_path = Path(arg1)
        if not pdf_path.exists():
            print(f"文件不存在: {pdf_path}")
            sys.exit(1)
        test_with_live_service(pdf_path, output_dir)


if __name__ == "__main__":
    main()
