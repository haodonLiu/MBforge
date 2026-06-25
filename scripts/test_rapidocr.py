"""Quick RapidOCR benchmark on a PDF file.

Usage:
    python scripts/test_rapidocr.py <path_to_pdf> [--pages N] [--dpi DPI]
"""

import sys
import time
import tempfile
import os

import fitz  # PyMuPDF


def pdf_to_images(pdf_path: str, dpi: int = 300, max_pages: int = 0) -> list[str]:
    doc = fitz.open(pdf_path)
    tmp_dir = tempfile.mkdtemp(prefix="rapidocr_bench_")
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    paths = []
    page_count = len(doc) if max_pages == 0 else min(len(doc), max_pages)
    for i in range(page_count):
        page = doc[i]
        out = os.path.join(tmp_dir, f"page_{i+1:04d}.png")
        page.get_pixmap(matrix=mat).save(out)
        paths.append(out)
    doc.close()
    return paths


_engine = None


def get_engine():
    global _engine
    if _engine is not None:
        return _engine
    from rapidocr import RapidOCR, EngineType, LangDet, LangRec, ModelType, OCRVersion
    _engine = RapidOCR(
        params={
            "Det.engine_type": EngineType.ONNXRUNTIME,
            "Det.lang_type": LangDet.EN,
            "Det.model_type": ModelType.MEDIUM,
            "Det.ocr_version": OCRVersion.PPOCRV6,
            "Det.providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
            "Rec.engine_type": EngineType.ONNXRUNTIME,
            "Rec.lang_type": LangRec.EN,
            "Rec.model_type": ModelType.MEDIUM,
            "Rec.ocr_version": OCRVersion.PPOCRV6,
            "Rec.providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
        }
    )
    return _engine


def run_rapidocr(image_path: str):
    import numpy as np
    from PIL import Image

    engine = get_engine()
    img = Image.open(image_path).convert("RGB")
    arr = np.array(img)

    t0 = time.perf_counter()
    out = engine(arr)
    elapsed = time.perf_counter() - t0

    if out is None or not getattr(out, "txts", None):
        return [], elapsed

    results = list(zip(out.boxes.tolist(), out.txts, list(out.scores)))
    return results, elapsed


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_rapidocr.py <pdf_path> [--pages N] [--dpi DPI]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    max_pages = 0
    dpi = 300

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--pages" and i + 1 < len(args):
            max_pages = int(args[i + 1])
            i += 2
        elif args[i] == "--dpi" and i + 1 < len(args):
            dpi = int(args[i + 1])
            i += 2
        else:
            i += 1

    print(f"PDF: {pdf_path}")
    print(f"DPI: {dpi}, Max pages: {max_pages or 'all'}")
    print()

    # Warm up engine (first call loads models)
    print("Loading GPU engine...")
    t_warmup = time.perf_counter()
    get_engine()
    print(f"Engine ready in {time.perf_counter() - t_warmup:.2f}s")
    print()

    # Convert PDF to images
    t0 = time.perf_counter()
    image_paths = pdf_to_images(pdf_path, dpi=dpi, max_pages=max_pages)
    convert_time = time.perf_counter() - t0
    print(f"PDF -> images: {len(image_paths)} pages in {convert_time:.2f}s")
    print()

    # OCR each page
    total_ocr_time = 0.0
    total_text_len = 0

    for idx, img_path in enumerate(image_paths):
        results, elapsed = run_rapidocr(img_path)
        total_ocr_time += elapsed
        text_len = sum(len(r[1]) for r in results)
        total_text_len += text_len
        print(f"  Page {idx+1}: {len(results)} blocks, {text_len} chars, {elapsed:.2f}s")

    print()
    print(f"=== Summary ===")
    print(f"Pages:        {len(image_paths)}")
    print(f"PDF convert:  {convert_time:.2f}s")
    print(f"OCR total:    {total_ocr_time:.2f}s")
    print(f"OCR per page: {total_ocr_time/len(image_paths):.2f}s")
    print(f"Total text:   {total_text_len} chars")
    print(f"Wall time:    {convert_time + total_ocr_time:.2f}s")


if __name__ == "__main__":
    main()
