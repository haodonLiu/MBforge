"""Test pipeline on first 20 pages of WO2026035726A1.PDF"""
import os, sys, tempfile, json, time
from pathlib import Path

# Read temp PDF path
with open(tempfile.gettempdir() + '/mbforge_test_20pg_path.txt') as f:
    TMP_PDF = f.read().strip()

print(f"PDF: {TMP_PDF}")
print(f"Size: {os.path.getsize(TMP_PDF)} bytes")
print("=" * 60)

# Temp library root
LIB_ROOT = Path(tempfile.mkdtemp(prefix="mbforge_test_20pg_"))
print(f"Library root: {LIB_ROOT}")
print("=" * 60)

# Import pipeline
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from mbforge.pipeline.runner import run_pipeline

def on_progress(evt):
    pct = ""
    from mbforge.pipeline.runner import STAGE_PCT
    if evt.stage in STAGE_PCT:
        pct = f" [{STAGE_PCT[evt.stage]}%]"
    print(f"  [{evt.stage}] {evt.event}: {evt.message}{pct}")

print("Starting pipeline...")
print("=" * 60)

t0 = time.time()
result = run_pipeline(
    pdf_path=str(TMP_PDF),
    library_root=str(LIB_ROOT),
    doc_id="WO2026035726A1_20pg",
    on_progress=on_progress,
)
elapsed = time.time() - t0

print("=" * 60)
print(f"Done in {elapsed:.1f}s")
print(f"  doc_id:    {result.doc_id}")
print(f"  pages:     {result.page_count}")
print(f"  parser:    {result.parser}")
print(f"  title:     {result.title}")
print(f"  indexed:   {result.indexed_count}")
print(f"  duration:  {result.duration_ms}ms")

# Check outputs
print("\nOutput files:")
for p in sorted(LIB_ROOT.rglob("*")):
    if p.is_file():
        rel = p.relative_to(LIB_ROOT)
        print(f"  {rel} ({p.stat().st_size} bytes)")

# Show report
report_file = LIB_ROOT / "storage" / "WO2026035726A1_20pg" / "report.json"
if report_file.exists():
    report = json.loads(report_file.read_text())
    print(f"\nReport: {json.dumps(report, indent=2, ensure_ascii=False)}")

# Show wiki summary
wiki_summary = LIB_ROOT / ".mbforge" / "openkb" / "wiki" / "wiki" / "summaries" / "tmp187l3fih_20pg.md"
if wiki_summary.exists():
    print(f"\nWiki summary:\n{wiki_summary.read_text()[:1000]}")

# Show indexed document first 500 chars
indexed_doc = LIB_ROOT / ".mbforge" / "openkb" / "documents" / "WO2026035726A1_20pg.md"
if indexed_doc.exists():
    text = indexed_doc.read_text()
    print(f"\nIndexed doc ({len(text)} chars):")
    print(text[:800])
