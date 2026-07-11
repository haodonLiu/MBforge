"""Run the refactored pipeline on two sample PDFs for integration validation."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mbforge.pipeline.runner import run_pipeline


def _emit(event) -> None:
    print(f"[{event.stage}] {event.event}: {event.message}", flush=True)


def main() -> int:
    library_root = Path(__file__).parent.parent / "runs" / "integration_pdfs"
    library_root.mkdir(parents=True, exist_ok=True)

    pdfs = [
        (
            "WO2026037254A1",
            Path("C:/Users/10954/Desktop/out_finetune/raw_pdf/WO2026037254A1.PDF"),
            "text-extractable",
        ),
        (
            "US20260027089A1",
            Path("C:/Users/10954/Desktop/out_finetune/raw_pdf/US20260027089A1.PDF"),
            "scanned",
        ),
    ]

    results = []
    for doc_id, pdf_path, kind in pdfs:
        print(f"\n=== {doc_id} ({kind}) ===", flush=True)
        start = time.monotonic()
        try:
            result = run_pipeline(
                str(pdf_path),
                str(library_root),
                doc_id=doc_id,
                on_progress=_emit,
            )
            duration = int((time.monotonic() - start) * 1000)
            results.append(
                {
                    "doc_id": result.doc_id,
                    "kind": kind,
                    "page_count": result.page_count,
                    "indexed_count": result.indexed_count,
                    "parser": result.parser,
                    "title": result.title,
                    "duration_ms": duration,
                    "status": "success",
                }
            )
        except Exception as exc:
            duration = int((time.monotonic() - start) * 1000)
            results.append(
                {
                    "doc_id": doc_id,
                    "kind": kind,
                    "status": "error",
                    "error": str(exc),
                    "duration_ms": duration,
                }
            )
            print(f"ERROR: {exc}", flush=True)

    summary_path = library_root / "integration_summary.json"
    summary_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nSummary written to: {summary_path}", flush=True)
    print(json.dumps(results, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
