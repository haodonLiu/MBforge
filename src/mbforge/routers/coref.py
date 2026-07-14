"""coref router - bridge from frontend to MolDetv2-FT detector.

Created 2026-07-08 as the replacement for the deleted stub-only coref.py.
Translates the FT detector's output into the KB-shaped FigureLabel[] and
CorefPrediction[] that the frontend's CorefBboxOverlay expects.

Input contract (matches frontend result_pane.ts):
    POST /api/v1/coref/figure-labels
        body: {libraryRoot, docId, page}
        -> {labels: FigureLabel[]}

    POST /api/v1/coref/predictions
        body: {libraryRoot, docId, page}
        -> {predictions: CorefPrediction[]}

The two calls share the same FT detection result internally; the frontend
makes both calls on the same page so the second call is cheap (we cache
per (libraryRoot, docId, page) for 30s).

OCR pass (added 2026-07-09): label bboxes from FT are cropped and run
through RapidOCRCropAdapter (concurrent batch via ThreadPoolExecutor) to
fill FigureLabel.label_text. OCR is best-effort: if the engine is
unavailable or a single crop fails, label_text falls back to a
synthetic "Label N" placeholder so the frontend still gets a non-empty
string. The synthetic fallback is the same shape as the real one so
the frontend's CorefBboxOverlay renders consistently.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from PIL import Image

from ..backends.ocr.rapidocr_adapter import RapidOCRCropAdapter
from ..core.artifact import ArtifactResolver, InvalidDocIdError
from ..parsers.molecule.coref_alt import detect_coref_via_ft_detector
from ..utils.helpers import ValidationError
from ..utils.logger import get_logger

logger = get_logger("mbforge.coref_router")

router = APIRouter()


# ---------------------------------------------------------------------------
# Per-page FT detection cache: 30s TTL keyed on (libraryRoot, docId, page).
# Avoids re-running YOLO on the second call (figure-labels + predictions
# share the same detection result).
# ---------------------------------------------------------------------------
_DETECT_TTL_SEC = 30.0
_detect_cache: dict[tuple[str, str, int], tuple[float, dict[str, Any]]] = {}

# Max worker threads for the label-region OCR batch. 4 balances
# concurrency vs DML GPU contention (each worker holds an ONNX
# session call). Raise to 6-8 on CPU-only machines; lower to 2 if
# DML errors with "out of memory" under heavy load.
OCR_MAX_WORKERS: int = 4


def _cached_detect(
    library_root: str, doc_id: str, page: int
) -> dict[str, Any] | None:
    """Run FT detection on a PDF page with a 30s per-page cache.

    Returns a dict with keys "labels" and "predictions" in KB shape, or
    None if FT detection is unavailable.
    """
    key = (library_root, doc_id, page)
    now = time.monotonic()
    cached = _detect_cache.get(key)
    if cached is not None and (now - cached[0]) < _DETECT_TTL_SEC:
        return cached[1]

    doc_path = _resolve_pdf_path(library_root, doc_id)
    if doc_path is None or not doc_path.exists():
        logger.warning(
            "PDF not found for project=%s doc=%s", library_root, doc_id
        )
        return None

    import fitz

    try:
        doc = fitz.open(str(doc_path))
    except Exception as e:
        logger.warning("Failed to open PDF %s: %s", doc_path, e)
        return None
    try:
        page_index = int(page) - 1
        if page_index < 0 or page_index >= doc.page_count:
            logger.debug(
                "Page out of range: page=%s doc=%s doc.page_count=%s",
                page, doc_id, doc.page_count,
            )
            return None
        fitz_page = doc.load_page(page_index)
        zoom = 300.0 / 72.0
        pix = fitz_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    finally:
        doc.close()

    import numpy as np
    from PIL import Image

    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n
    )
    image = Image.fromarray(img_array)

    try:
        coref_result = detect_coref_via_ft_detector(image)
    except Exception as e:
        logger.warning("FT detection failed for page %s: %s", page, e)
        return None
    # OCR pass: run batch OCR on the label-region crops. Best-effort:
    # if the adapter is unavailable or the batch fails, we get a list
    # of empty strings and label_text falls back to synthetic in
    # _coref_to_kb_shapes below.
    ocr_texts = _run_label_ocr(image, coref_result)

    labels, predictions = _coref_to_kb_shapes(
        coref_result=coref_result,
        page=page,
        doc_id=doc_id,
        ocr_texts=ocr_texts,
    )
    result = {"labels": labels, "predictions": predictions}
    _detect_cache[key] = (now, result)
    if len(_detect_cache) > 256:
        cutoff = now - _DETECT_TTL_SEC
        for k, (ts, _) in list(_detect_cache.items()):
            if ts < cutoff:
                _detect_cache.pop(k, None)
    return result


def _resolve_pdf_path(library_root: str, doc_id: str) -> Path | None:
    """Resolve the absolute PDF path for a (libraryRoot, docId) pair.

    Best-effort: checks the project root for any file matching the doc_id
    or the canonical library_storage conventions. Returns None on miss
    so the caller can return an empty result gracefully.
    """
    root = Path(library_root)
    if not root.exists():
        return None
    try:
        canonical_source = ArtifactResolver(root).source_pdf(doc_id)
    except InvalidDocIdError:
        return None
    candidates = [
        canonical_source,
        root / f"{doc_id}.pdf",
        root / "docs" / f"{doc_id}.pdf",
        root / doc_id / "source.pdf",
        root / doc_id / f"{doc_id}.pdf",
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    try:
        for child in root.iterdir():
            if (
                child.is_file()
                and child.suffix.lower() == ".pdf"
                and doc_id in child.name
            ):
                return child
    except (PermissionError, OSError):
        pass
    return None

def _crop_label_boxes(
    image: Any,
    bboxes: list[Any],
    padding: float = 0.1,
) -> list[Any]:
    """Crop label-region PIL Images from the rendered page.

    Only ``category_id == 3`` bboxes (identifiers) are cropped. Each crop
    has 10% padding on all sides so label characters that extend past
    the FT-detected bbox edge are still picked up by OCR.

    Returns one crop per label, in the same order as ``bboxes``. Empty
    boxes (e.g. width <= 0) are skipped and the corresponding entry in
    the returned list is a 1x1 white image — the OCR engine will
    gracefully return "" for that, and the caller falls back to the
    synthetic label.
    """
    w, h = image.size
    crops: list[Any] = []
    for cb in bboxes:
        if cb.category_id != 3:
            continue
        x1, y1, x2, y2 = cb.bbox
        bw = x2 - x1
        bh = y2 - y1
        pad_w = bw * padding
        pad_h = bh * padding
        px1 = max(0, int((x1 - pad_w) * w))
        py1 = max(0, int((y1 - pad_h) * h))
        px2 = min(w, int((x2 + pad_w) * w))
        py2 = min(h, int((y2 + pad_h) * h))
        if px2 <= px1 or py2 <= py1:
            crops.append(Image.new("RGB", (1, 1), (255, 255, 255)))
            continue
        crops.append(image.crop((px1, py1, px2, py2)))
    return crops


def _run_label_ocr(image: Any, coref_result: Any) -> list[str]:
    """Crop label bboxes and run batch OCR.

    Returns one text per label in the same order as
    ``coref_result.bboxes`` filtered to category_id == 3. Length of
    the returned list equals the number of label bboxes.

    Return value details:
      - No labels (no category_id == 3 bboxes): returns ``[]`` (empty
        list, NOT ``[""] * 0`` - they're equal but the empty-list
        branch is the actual code path for the no-labels case).
      - Adapter unavailable or batch fails: returns ``[""] * N`` so
        ``_coref_to_kb_shapes`` falls back to synthetic "Label N"
        for every label.
      - Per-crop failures inside the batch are returned as "" by the
        adapter itself and do not affect other crops.
    """
    crops = _crop_label_boxes(image, coref_result.bboxes)
    if not crops:
        return []
    try:
        adapter = RapidOCRCropAdapter.instance()
    except Exception as e:  # noqa: BLE001 - adapter init may fail
        logger.debug("RapidOCRCropAdapter unavailable: %s", e)
        return [""] * len(crops)
    try:
        return adapter.readtext_batch(crops, max_workers=OCR_MAX_WORKERS)
    except Exception as e:  # noqa: BLE001 - inference can fail on weird crops
        logger.warning("Batch OCR failed: %s", e)
        return [""] * len(crops)


def _coref_to_kb_shapes(
    coref_result: Any,
    page: int,
    doc_id: str,
    ocr_texts: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Translate CorefResult to FigureLabel[] + CorefPrediction[] KB shapes.

    FigureLabel fields used by frontend: id, doc_id, page, label_bbox,
    label_text, ocr_conf, image_path.

    CorefPrediction fields used by frontend: id, doc_id, page, mol_bbox,
    mol_smiles, label_bbox, label_text, label_id, confidence, source,
    is_confirmed, image_path.
    """
    labels: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    # Build labels (category_id=3) and a label_id -> text map for O(1)
    bbox_idx_to_label_id: dict[int, int] = {}
    label_id_to_text: dict[int, str] = {}
    label_idx_counter = 0
    for _bbox_idx, cb in enumerate(coref_result.bboxes):
        if cb.category_id != 3:
            continue
        label_id = label_idx_counter + 1
        bbox_idx_to_label_id[_bbox_idx] = label_id
        label_idx_counter += 1
        # Pull OCR text for this label; fall back to synthetic on empty.
        ocr_text_for_label = (
            ocr_texts[label_idx_counter - 1]
            if label_idx_counter - 1 < len(ocr_texts)
            else ""
        )
        label_text = ocr_text_for_label if ocr_text_for_label else f"Label {label_id}"
        labels.append(
            {
                "id": label_id,
                "doc_id": doc_id,
                "page": page,
                "label_bbox": list(cb.bbox),
                "label_text": label_text,
                "ocr_conf": float(cb.score),
                "image_path": None,
            }
        )
        label_id_to_text[label_id] = label_text

    pred_id = 0
    for mol_bbox_idx, idt_bbox_idx in coref_result.corefs:
        if mol_bbox_idx >= len(coref_result.bboxes):
            continue
        mol_cb = coref_result.bboxes[mol_bbox_idx]
        if mol_cb.category_id != 1:
            continue
        idt_cb = (
            coref_result.bboxes[idt_bbox_idx]
            if idt_bbox_idx < len(coref_result.bboxes)
            else None
        )
        # O(1) lookup: bbox_idx -> label_id -> label_text
        idt_label_id = bbox_idx_to_label_id.get(idt_bbox_idx)
        pred_label_text = (
            label_id_to_text.get(idt_label_id)
            if idt_label_id is not None
            else None
        )
        pred_id += 1
        predictions.append(
            {
                "id": pred_id,
                "doc_id": doc_id,
                "page": page,
                "mol_smiles": None,
                "mol_bbox": list(mol_cb.bbox),
                "mol_conf": float(mol_cb.score),
                "label_id": idt_label_id,
                "label_text": pred_label_text,
                "label_bbox": list(idt_cb.bbox) if idt_cb is not None else None,
                "confidence": float(mol_cb.score),
                "source": "geometric_ft",
                "is_confirmed": False,
                "image_path": None,
            }
        )
    return labels, predictions


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/figure-labels")
async def get_figure_labels(body: dict) -> dict:
    """Return FigureLabel[] for a (project, doc, page) via FT detector."""
    library_root = body.get("libraryRoot") or body.get("library_root") or ""
    doc_id = body.get("docId") or body.get("doc_id") or ""
    page = body.get("page")
    if not library_root or not doc_id or not isinstance(page, int):
        raise ValidationError(
            "libraryRoot, docId, and integer page are required"
        )

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: _cached_detect(library_root, doc_id, page)
    )
    if result is None:
        return {"labels": []}
    return {"labels": result["labels"]}


@router.post("/predictions")
async def get_coref_predictions(body: dict) -> dict:
    """Return CorefPrediction[] for a (project, doc, page) via FT detector."""
    library_root = body.get("libraryRoot") or body.get("library_root") or ""
    doc_id = body.get("docId") or body.get("doc_id") or ""
    page = body.get("page")
    if not library_root or not doc_id or not isinstance(page, int):
        raise ValidationError(
            "libraryRoot, docId, and integer page are required"
        )

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: _cached_detect(library_root, doc_id, page)
    )
    if result is None:
        return {"predictions": []}
    return {"predictions": result["predictions"]}
