"""端到端真实PDF全流程测试 — MolDet+MolScribe+上下文关联+KB入库

测试对象：US20260027089A1.PDF (扫描型专利, 4MB, 200+化合物+E0XX+pIC50)
流程：
  1. PyMuPDF 渲染含分子图的页面
  2. MolDetv2-Doc 检测分子bbox (HTTP /api/v1/moldet/extract-page)
  3. 解析markdown表格 (E001..E223 + pIC50)
  4. 关联: 检测到的分子bbox ↔ 化合物ID ↔ pIC50值
  5. 把关联结果存到Rust FTS5 KB
  6. 验证可检索
"""
import asyncio, base64, json, re, sys
import io
# Force UTF-8 stdout (Windows subprocess from Start-Process defaults to GBK)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from pathlib import Path
import httpx
import fitz  # PyMuPDF

PDF = Path(r"C:\Users\10954\Desktop\MBForge\e2e_test\US20260027089A1.PDF")
MD  = Path(r"C:\Users\10954\Desktop\MBForge\e2e_test\output\patent_us20260027089_02_extracted.md")
OUT = Path(r"C:\Users\10954\Desktop\MBForge\e2e_test\output")
OUT.mkdir(exist_ok=True)
API = "http://127.0.0.1:18792"

# ──────────────────────────────────────────────
# 解析 markdown 找 pIC50 表格 → 化合物+结构图+pIC50
# ──────────────────────────────────────────────
def parse_pic50_table(md_text: str) -> list[dict]:
    """解析 <tr><td>E001</td><td><img.../></td><td>6.4</td></tr> 模式"""
    pat = re.compile(
        r'<tr>\s*<td>(E\d+)</td>\s*'
        r'<td>(?:<img\s+src="([^"]*)"[^/]*/?>)?\s*</td>\s*'
        r'<td>([\d.]+)</td>\s*</tr>',
        re.IGNORECASE
    )
    # 简化版: 行内顺序可能不同
    entries = []
    for line in md_text.split("\n"):
        # 形如: <tr><td>E001</td><td><img src="..."/></td><td>6.4</td></tr>
        m = re.search(r'<td>\s*(E\d+)\s*</td>.*?<td>([\d.]+)\s*</td>', line)
        if m:
            cid, val = m.group(1), float(m.group(2))
            entries.append({"compound_id": cid, "pIC50": val, "raw_line": line.strip()})
    return entries

# ──────────────────────────────────────────────
# 渲染 PDF 页面到 PNG
# ──────────────────────────────────────────────
def render_page(doc, page_idx, dpi=200) -> tuple[bytes, int, int, float, float]:
    page = doc[page_idx]
    mat = fitz.Matrix(dpi/72, dpi/72)
    pix = page.get_pixmap(matrix=mat)
    return pix.tobytes("png"), pix.width, pix.height, float(page.rect.width), float(page.rect.height)

# ──────────────────────────────────────────────
# 异步调用 MolDetv2-Doc 检测
# ──────────────────────────────────────────────
async def detect_molecules(client, img_b64, page_idx, w, h, wp, hp, dpi):
    payload = {
        "image_base64": img_b64,
        "page_idx": page_idx,
        "image_w": w, "image_h": h,
        "page_w_pts": wp, "page_h_pts": hp,
        "dpi": float(dpi),
    }
    try:
        r = await client.post(f"{API}/api/v1/moldet/extract-page", json=payload, timeout=120.0)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}: {r.text[:200]}"
        return r.json(), None
    except Exception as e:
        return None, str(e)

# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────
async def main():
    print("="*70)
    print("E2E Pipeline: PDF → MolDet → Context Association → KB")
    print("="*70)

    # 1. 解析 markdown 找所有化合物+pIC50
    md_text = MD.read_text(encoding="utf-8")
    pic50_entries = parse_pic50_table(md_text)
    print(f"\n[1] Parsed {len(pic50_entries)} compound-pIC50 pairs from markdown")
    if pic50_entries:
        for e in pic50_entries[:5]:
            print(f"    {e['compound_id']:6s}  pIC50={e['pIC50']}")
        print(f"    ... +{len(pic50_entries)-5} more")
    (OUT / "pic50_table.json").write_text(
        json.dumps(pic50_entries, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 2. 找pIC50表所在页
    # 经验: 页码从E001开始, 每页≈7-14个化合物, 估E001在page 36
    doc = fitz.open(PDF)
    print(f"\n[2] PDF has {len(doc)} pages")

    # 试第36-45页 (E001在page 36左右, 0-indexed)
    test_pages = list(range(36, 45))

    # 3. 检测 + 关联
    all_detections = []
    async with httpx.AsyncClient(timeout=120.0) as client:
        for pidx in test_pages:
            img_bytes, w, h, wp, hp = render_page(doc, pidx, dpi=200)
            img_b64 = base64.b64encode(img_bytes).decode()
            print(f"\n[3] Page {pidx+1}: rendered {w}x{h} ({len(img_bytes)//1024} KB)")

            t0 = asyncio.get_event_loop().time()
            result, err = await detect_molecules(client, img_b64, pidx, w, h, wp, hp, 200)
            dt = asyncio.get_event_loop().time() - t0

            if err:
                print(f"    [X] MolDet error: {err}")
                break

            count = result.get("count", 0)
            results = result.get("results", [])
            print(f"    [OK] MolDetv2-Doc: {count} regions detected ({dt:.1f}s)")
            for r in results[:5]:
                bbox_pdf = r.get("bbox_pdf", [])
                conf = r.get("moldet_conf", 0)
                print(f"      bbox_pdf={bbox_pdf} conf={conf:.2f} status={r.get('status')}")
            all_detections.append({
                "page_idx": pidx,
                "page_w": w, "page_h": h,
                "detection_count": count,
                "results": results,
            })

            if len(all_detections) >= 3:  # 测3页足够
                break

    doc.close()

    # 4. 关联：检测到的分子 ↔ 化合物+活性
    # 启发式: 每页~10个化合物 + 1-3个分子, 假设同页内按顺序对应
    associations = []
    cid_iter = iter(pic50_entries)
    for det in all_detections:
        for mol in det["results"]:
            try:
                entry = next(cid_iter)
            except StopIteration:
                break
            associations.append({
                "compound_id": entry["compound_id"],
                "pIC50": entry["pIC50"],
                "page": det["page_idx"] + 1,
                "bbox_pdf": mol.get("bbox_pdf"),
                "moldet_conf": mol.get("moldet_conf"),
                "context": entry["raw_line"][:200],
            })

    print(f"\n[4] Associated {len(associations)} molecules with compound data:")
    for a in associations[:10]:
        print(f"    {a['compound_id']:6s}  pIC50={a['pIC50']:.1f}  page={a['page']}  conf={a['moldet_conf']:.2f}")

    (OUT / "associations.json").write_text(
        json.dumps(associations, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 5. 存到 Rust KB (通过 HTTP API)
    print(f"\n[5] Indexing to KB...")
    # 把关联转成 section 文本
    sections = []
    for a in associations:
        text = (
            f"Compound {a['compound_id']}: pIC50 = {a['pIC50']} "
            f"(MrpgrX2 antagonist, detected on page {a['page']}, "
            f"moldet_conf={a['moldet_conf']:.2f})"
        )
        sections.append({
            "title": f"Compound {a['compound_id']}",
            "path": f"compounds/{a['compound_id']}",
            "text": text,
            "page_start": a["page"],
            "page_end": a["page"],
        })
    kb_payload = {
        "project_root": str(PDF.parent),
        "doc_id": "test_patent_mol_pipeline",
        "filename": PDF.name,
        "sections": sections,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{API}/api/v1/kb/index-sections", json=kb_payload)
        if r.status_code == 200:
            data = r.json()
            print(f"    [OK] Indexed {data.get('indexed', '?')} sections")
        else:
            print(f"    [X] KB index failed: HTTP {r.status_code}: {r.text[:200]}")

    # 6. 检索验证
    print(f"\n[6] KB search verification:")
    queries = ["E001", "E041 pIC50", "MrpgrX2 antagonist", "compound"]
    async with httpx.AsyncClient(timeout=30.0) as client:
        for q in queries:
            r = await client.post(f"{API}/api/v1/kb/search", json={
                "project_root": str(PDF.parent),
                "query": q,
                "top_k": 3,
            })
            if r.status_code == 200:
                data = r.json()
                results = data.get("results", [])
                print(f"    '{q}' → {len(results)} hits")
                for hit in results[:2]:
                    print(f"      • {hit.get('text', '')[:100]}")
            else:
                print(f"    '{q}' → HTTP {r.status_code}")

    print(f"\n✓ Done. Outputs in: {OUT}")

asyncio.run(main())
