"""Debug molecule detection pipeline"""
import sys, os, tempfile, json
from pathlib import Path

sys.path.insert(0, 'src')

# Setup
LIB_ROOT = Path(tempfile.mkdtemp(prefix="mbforge_debug_"))
print(f"Library root: {LIB_ROOT}")

# Read 20pg PDF
with open(tempfile.gettempdir() + '/mbforge_test_20pg_path.txt') as f:
    TMP_PDF = f.read().strip()

# Direct call to extract_molecules_from_pdf to debug
from mbforge.pipeline.extract_molecules import extract_molecules_from_pdf
from mbforge.pipeline.normalize import normalize_molecules

# Get raw image_results
from mbforge.backends.moldet_v2_ft import MolDetv2FTDetector
from mbforge.parsers.molecule.coref_alt import detect_coref_via_ft_detector
from mbforge.core.resource_manager import ResourceManager
from mbforge.parsers.molecule.extraction_result import ExtractionResult

ResourceManager.ensure("moldet")
detector = MolDetv2FTDetector()
print(f"Detector available: {detector.is_available()}")

# Load PDF and process manually with detailed logging
import fitz
from PIL import Image
import numpy as np
from mbforge.backends import molscribe

molscribe.load()

doc = fitz.open(TMP_PDF)
print(f"\nProcessing {doc.page_count} pages...")

all_results = []
for page_idx in range(min(doc.page_count, 5)):  # Just first 5 pages for debug
    page = doc.load_page(page_idx)
    text = page.get_text("text").strip()
    has_imgs = len(page.get_images()) > 0
    if len(text) > 500 and not has_imgs:
        print(f"  Page {page_idx}: skip (text-only, {len(text)} chars)")
        continue

    zoom = 200 / 72
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    image = Image.fromarray(img_array)

    coref_result = detect_coref_via_ft_detector(image)
    print(f"  Page {page_idx}: {len(coref_result.bboxes)} bboxes, mols={sum(1 for b in coref_result.bboxes if b.category_id==1)}, idts={sum(1 for b in coref_result.bboxes if b.category_id==3)}")

    for mol_idx, cb in enumerate(coref_result.bboxes):
        if cb.category_id != 1:
            continue
        px1 = int(round(cb.bbox[0] * pix.width))
        py1 = int(round(cb.bbox[1] * pix.height))
        px2 = int(round(cb.bbox[2] * pix.width))
        py2 = int(round(cb.bbox[3] * pix.height))
        if px2 <= px1 or py2 <= py1:
            continue
        crop = image.crop((px1, py1, px2, py2)).convert("L")
        try:
            scribe = molscribe.predict(crop)
            smi = scribe.esmiles or ""
            print(f"    Mol {mol_idx}: MolScribe esmiles={smi!r}, conf={scribe.confidence}")
        except Exception as e:
            print(f"    Mol {mol_idx}: MolScribe failed: {e}")
            smi = ""

        all_results.append(ExtractionResult(
            esmiles=smi,
            name="",
            source="image",
            moldet_conf=cb.score,
            scribe_conf=scribe.confidence if smi else 0.0,
            composite_conf=cb.score,
            bbox_pdf=[px1, py1, px2, py2],
            page_idx=page_idx,
            context_text="",
            mol_img_path=None,
            status="pending",
            properties={},
        ))

doc.close()

print(f"\nTotal extraction results: {len(all_results)}")
for r in all_results:
    print(f"  page={r.page_idx}, esmiles={r.esmiles!r}, conf={r.composite_conf}")

# Normalize
print(f"\nNormalizing {len(all_results)} results...")
normalized = normalize_molecules(all_results)
print(f"Normalized: {len(normalized)}")
for n in normalized:
    print(f"  status={n.status}, esmiles={n.esmiles!r}, reason={n.reject_reason}")

# Save crop files for inspection
print(f"\nCrops saved in {LIB_ROOT / '.mbforge' / 'crops'}")