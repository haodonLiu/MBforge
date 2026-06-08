"""测试 MolDetect coref 功能"""

import sys
import base64
from pathlib import Path
from io import BytesIO

def render_pdf_page(pdf_path: str, page_num: int, dpi: int = 150) -> bytes:
    """渲染 PDF 页面为 PNG 图像"""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        page = doc.load_page(page_num - 1)  # 0-indexed
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        doc.close()
        return img_bytes
    except ImportError:
        print("Error: PyMuPDF (fitz) not installed. Run: pip install PyMuPDF")
        sys.exit(1)


def test_coref_endpoint(image_bytes: bytes, page_num: int):
    """测试 coref 端点"""
    import requests

    url = "http://127.0.0.1:18792/api/v1/moldet/coref"

    # 编码图像为 base64
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "image_base64": image_b64,
        "use_molscribe": True,
        "use_ocr": True,
    }

    print(f"  Calling coref endpoint...")
    try:
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()
        return result
    except requests.exceptions.RequestException as e:
        print(f"  Error: {e}")
        return None


def analyze_result(result: dict, page_num: int):
    """分析 coref 结果"""
    bboxes = result.get("bboxes", [])
    corefs = result.get("corefs", [])

    # 统计
    mol_count = sum(1 for b in bboxes if b.get("category_id") == 1)
    idt_count = sum(1 for b in bboxes if b.get("category_id") == 3)

    print(f"\n  Page {page_num} Results:")
    print(f"    Total bboxes: {len(bboxes)}")
    print(f"    Molecules (category_id=1): {mol_count}")
    print(f"    Identifiers (category_id=3): {idt_count}")
    print(f"    Coref pairs: {len(corefs)}")

    # 显示分子详情
    print(f"\n  Molecules:")
    for i, bbox in enumerate(bboxes):
        if bbox.get("category_id") == 1:
            smiles = bbox.get("smiles", "")
            score = bbox.get("score", 0)
            print(f"    [{i}] score={score:.3f}, smiles={smiles[:50] if smiles else '(none)'}")

    # 显示标识符详情
    print(f"\n  Identifiers:")
    for i, bbox in enumerate(bboxes):
        if bbox.get("category_id") == 3:
            text = bbox.get("text", "")
            score = bbox.get("score", 0)
            print(f"    [{i}] score={score:.3f}, text={text}")

    # 显示 coref 关系
    print(f"\n  Coref pairs (molecule -> identifier):")
    for mol_idx, idt_idx in corefs:
        mol = bboxes[mol_idx] if mol_idx < len(bboxes) else None
        idt = bboxes[idt_idx] if idt_idx < len(bboxes) else None
        if mol and idt:
            smiles = mol.get("smiles", "")[:30]
            text = idt.get("text", "")
            print(f"    Molecule[{mol_idx}] ({smiles}...) -> Identifier[{idt_idx}] ({text})")


def main():
    pdf_files = [
        r"C:\Users\10954\Desktop\CN120118069A.PDF",
        r"C:\Users\10954\Desktop\US20260027089A1.PDF",
    ]

    # 测试的页面（选择有分子的页面）
    test_pages = {
        r"C:\Users\10954\Desktop\CN120118069A.PDF": [49, 61, 66],
        r"C:\Users\10954\Desktop\US20260027089A1.PDF": [5, 10, 15],
    }

    print("=" * 60)
    print("MolDetect Coref 功能测试")
    print("=" * 60)

    for pdf_path in pdf_files:
        if not Path(pdf_path).exists():
            print(f"\n[SKIP] PDF not found: {pdf_path}")
            continue

        print(f"\n{'=' * 60}")
        print(f"Testing: {Path(pdf_path).name}")
        print(f"{'=' * 60}")

        pages = test_pages.get(pdf_path, [1])

        for page_num in pages:
            print(f"\n--- Page {page_num} ---")

            # 渲染页面
            print(f"  Rendering page {page_num}...")
            try:
                image_bytes = render_pdf_page(pdf_path, page_num)
                print(f"  Rendered: {len(image_bytes)} bytes")
            except Exception as e:
                print(f"  Error rendering: {e}")
                continue

            # 调用 coref
            result = test_coref_endpoint(image_bytes, page_num)
            if result is None:
                continue

            # 分析结果
            analyze_result(result, page_num)

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
