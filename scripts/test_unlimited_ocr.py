"""Test Unlimited-OCR batch inference on PDF pages.

Usage:
    python scripts/test_unlimited_ocr.py <pdf_path> [--pages N] [--batch B] [--dpi DPI]
"""

import sys
import time
import tempfile
import os

import fitz  # PyMuPDF
import torch
from transformers import AutoModel, AutoTokenizer


def pdf_to_images(pdf_path: str, dpi: int = 300, max_pages: int = 0) -> list[str]:
    doc = fitz.open(pdf_path)
    tmp_dir = tempfile.mkdtemp(prefix="unlimited_ocr_")
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


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_unlimited_ocr.py <pdf_path> [--pages N] [--batch B] [--dpi DPI]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    max_pages = 20
    batch_size = 5
    dpi = 300

    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--pages" and i + 1 < len(args):
            max_pages = int(args[i + 1])
            i += 2
        elif args[i] == "--batch" and i + 1 < len(args):
            batch_size = int(args[i + 1])
            i += 2
        elif args[i] == "--dpi" and i + 1 < len(args):
            dpi = int(args[i + 1])
            i += 2
        else:
            i += 1

    print(f"PDF: {pdf_path}")
    print(f"DPI: {dpi}, Pages: {max_pages}, Batch: {batch_size}")
    print()

    # Check GPU
    if not torch.cuda.is_available():
        print("ERROR: CUDA not available")
        sys.exit(1)

    gpu_name = torch.cuda.get_device_name(0)
    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
    print(f"GPU: {gpu_name} ({vram_gb:.1f} GB VRAM)")
    print()

    # Load model
    print("Loading Unlimited-OCR model...")
    t0 = time.perf_counter()
    model_name = "baidu/Unlimited-OCR"
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        model_name,
        trust_remote_code=True,
        use_safetensors=True,
        torch_dtype=torch.bfloat16,
    )
    model = model.eval().cuda()
    load_time = time.perf_counter() - t0
    print(f"Model loaded in {load_time:.1f}s")
    print()

    # Convert PDF to images
    t0 = time.perf_counter()
    image_paths = pdf_to_images(pdf_path, dpi=dpi, max_pages=max_pages)
    convert_time = time.perf_counter() - t0
    print(f"PDF -> images: {len(image_paths)} pages in {convert_time:.2f}s")
    print()

    # Process in batches
    total_pages = len(image_paths)
    total_ocr_time = 0.0

    for batch_start in range(0, total_pages, batch_size):
        batch_end = min(batch_start + batch_size, total_pages)
        batch_paths = image_paths[batch_start:batch_end]

        print(f"Batch {batch_start//batch_size + 1}: pages {batch_start+1}-{batch_end}")

        t0 = time.perf_counter()
        try:
            # Use infer_multi for batch processing
            output = model.infer_multi(
                tokenizer,
                prompt="<image>Multi page parsing.",
                image_files=batch_paths,
                output_path=tempfile.mkdtemp(prefix="ocr_out_"),
                image_size=1024,
                max_length=32768,
                no_repeat_ngram_size=35,
                ngram_window=1024,
                save_results=False,
            )
            elapsed = time.perf_counter() - t0
            total_ocr_time += elapsed
            print(f"  Done in {elapsed:.2f}s")

            # Check VRAM usage
            vram_used = torch.cuda.memory_allocated() / 1024**3
            vram_reserved = torch.cuda.memory_reserved() / 1024**3
            print(f"  VRAM: {vram_used:.1f}GB used, {vram_reserved:.1f}GB reserved")

        except torch.cuda.OutOfMemoryError:
            elapsed = time.perf_counter() - t0
            print(f"  OOM after {elapsed:.2f}s!")
            torch.cuda.empty_cache()

            # Try with smaller batch
            if batch_size > 1:
                print(f"  Retrying with batch_size=1...")
                for single_path in batch_paths:
                    try:
                        t1 = time.perf_counter()
                        model.infer_multi(
                            tokenizer,
                            prompt="<image>Multi page parsing.",
                            image_files=[single_path],
                            output_path=tempfile.mkdtemp(prefix="ocr_out_"),
                            image_size=1024,
                            max_length=32768,
                            no_repeat_ngram_size=35,
                            ngram_window=1024,
                            save_results=False,
                        )
                        single_elapsed = time.perf_counter() - t1
                        total_ocr_time += single_elapsed
                        print(f"    Single page OK: {single_elapsed:.2f}s")
                    except torch.cuda.OutOfMemoryError:
                        print(f"    Single page also OOM - page too large for VRAM")
                        torch.cuda.empty_cache()
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"  Error after {elapsed:.2f}s: {e}")

        # Free memory between batches
        torch.cuda.empty_cache()
        print()

    print(f"=== Summary ===")
    print(f"Pages:          {total_pages}")
    print(f"PDF convert:    {convert_time:.2f}s")
    print(f"OCR total:      {total_ocr_time:.2f}s")
    print(f"OCR per page:   {total_ocr_time/total_pages:.2f}s")
    print(f"Wall time:      {convert_time + total_ocr_time:.2f}s")


if __name__ == "__main__":
    main()
