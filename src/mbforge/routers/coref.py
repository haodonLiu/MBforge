"""coref router - bridge from frontend to MolDetv2-FT detector + KB store.

Created 2026-07-08 as the replacement for the deleted stub-only coref.py.
Translates the FT detector's output into the KB-shaped FigureLabel[] and
CorefPrediction[] that the frontend's CorefBboxOverlay expects.

Persistence (2026-07-14): first read for a (doc, page) runs FT detection,
writes into ``figure_labels`` / ``coref_predictions``, and returns stable
AUTOINCREMENT ids. Subsequent reads hit the DB so confirm/update survive
refresh. In-memory 30s cache is only a FT-side optimization for cold miss
double-calls (labels + predictions).

Input contract (matches frontend result_pane.ts):
    POST /api/v1/coref/figure-labels
    POST /api/v1/coref/predictions
    POST /api/v1/coref/ensure-for-image
    POST /api/v1/coref/confirm-prediction
    POST /api/v1/coref/update-pair
    POST /api/v1/coref/molecule-chain
    POST /api/v1/coref/page-parse-result
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter
from PIL import Image

from ..backends.ocr.rapidocr_adapter import RapidOCRCropAdapter
from ..core.database import DatabaseManager
from ..parsers.molecule.coref_alt import detect_coref_via_ft_detector
from ..utils.helpers import ValidationError
from ..utils.logger import get_logger
from ._path_utils import (
    DocumentNotFoundError,
    resolve_library_root,
    resolve_pdf_path,
    validate_doc_id,
)

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

    try:
        doc_path = resolve_pdf_path(library_root, doc_id)
    except DocumentNotFoundError:
        # Missing documents surface as empty results; traversal/validation
        # errors are left to propagate to the central MBForgeError handler.
        logger.warning("PDF not found for library=%s doc=%s", library_root, doc_id)
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
# KB persistence helpers
# ---------------------------------------------------------------------------


def _bbox_to_text(bbox: list[float] | tuple[float, ...] | None) -> str | None:
    if bbox is None:
        return None
    return json.dumps([float(x) for x in bbox])


def _bbox_from_text(raw: str | None) -> list[float] | None:
    if not raw:
        return None
    try:
        val = json.loads(raw)
        if isinstance(val, list):
            return [float(x) for x in val]
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    # Migration-test style: "10,20,30,40"
    try:
        parts = [float(p) for p in raw.split(",")]
        if len(parts) == 4:
            return parts
    except ValueError:
        pass
    return None


def _parse_page_body(body: dict) -> tuple[str, str, int]:
    library_root = body.get("libraryRoot") or body.get("library_root") or ""
    doc_id = body.get("docId") or body.get("doc_id") or ""
    page = body.get("page")
    if not library_root or not doc_id or not isinstance(page, int):
        raise ValidationError("libraryRoot, docId, and integer page are required")
    resolve_library_root(library_root)
    validate_doc_id(doc_id)
    return library_root, doc_id, page


def _row_to_label(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "doc_id": row["doc_id"],
        "page": int(row["page"]),
        "label_bbox": _bbox_from_text(row["label_bbox"]),
        "label_text": row["label_text"],
        "ocr_conf": row["ocr_conf"],
        "image_path": row["image_path"],
    }


def _row_to_prediction(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "doc_id": row["doc_id"],
        "page": int(row["page"]),
        "mol_smiles": row["mol_smiles"],
        "mol_bbox": _bbox_from_text(row["mol_bbox"]),
        "mol_conf": row["mol_conf"],
        "label_id": row["label_id"],
        "label_text": row["label_text"],
        "label_bbox": _bbox_from_text(row["label_bbox"]),
        "confidence": row["confidence"],
        "source": row["source"] or "geometric",
        "is_confirmed": bool(row["is_confirmed"]),
        "image_path": row["image_path"],
    }


def _load_page_from_db(
    library_root: str, doc_id: str, page: int
) -> dict[str, list[dict[str, Any]]] | None:
    """Return persisted labels+predictions for a page, or None if empty."""
    db = DatabaseManager.get(library_root)
    db.initialize()
    with db.kb_conn() as conn:
        labels = conn.execute(
            "SELECT * FROM figure_labels WHERE doc_id = ? AND page = ? ORDER BY id",
            (doc_id, page),
        ).fetchall()
        preds = conn.execute(
            "SELECT * FROM coref_predictions WHERE doc_id = ? AND page = ? ORDER BY id",
            (doc_id, page),
        ).fetchall()
    if not labels and not preds:
        return None
    return {
        "labels": [_row_to_label(r) for r in labels],
        "predictions": [_row_to_prediction(r) for r in preds],
    }


def _persist_page(
    library_root: str,
    doc_id: str,
    page: int,
    labels: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    image_path: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Insert FT output; return rows with stable AUTOINCREMENT ids.

    Ephemeral FT ids are remapped: label ephemeral id -> DB id, then
    prediction.label_id is rewritten to the DB label id.
    """
    db = DatabaseManager.get(library_root)
    db.initialize()
    eph_label_to_db: dict[int, int] = {}
    with db.kb_conn() as conn:
        for lab in labels:
            eph_id = int(lab["id"])
            cur = conn.execute(
                """
                INSERT INTO figure_labels
                    (doc_id, page, label_bbox, label_text, ocr_conf, image_path)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    page,
                    _bbox_to_text(lab.get("label_bbox")),
                    lab.get("label_text"),
                    lab.get("ocr_conf"),
                    image_path if image_path is not None else lab.get("image_path"),
                ),
            )
            eph_label_to_db[eph_id] = int(cur.lastrowid)

        for pred in predictions:
            eph_label_id = pred.get("label_id")
            db_label_id = (
                eph_label_to_db.get(int(eph_label_id))
                if eph_label_id is not None
                else None
            )
            # UNIQUE(doc_id, page, mol_smiles, label_text) — FT often has
            # mol_smiles=NULL; store empty string to keep uniqueness useful.
            mol_smiles = pred.get("mol_smiles") or ""
            conn.execute(
                """
                INSERT INTO coref_predictions
                    (doc_id, page, mol_smiles, mol_bbox, mol_conf,
                     label_id, label_text, label_bbox, confidence,
                     source, is_confirmed, image_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    page,
                    mol_smiles,
                    _bbox_to_text(pred.get("mol_bbox")),
                    pred.get("mol_conf"),
                    db_label_id,
                    pred.get("label_text"),
                    _bbox_to_text(pred.get("label_bbox")),
                    pred.get("confidence"),
                    pred.get("source") or "geometric_ft",
                    1 if pred.get("is_confirmed") else 0,
                    image_path if image_path is not None else pred.get("image_path"),
                ),
            )

    stored = _load_page_from_db(library_root, doc_id, page)
    return stored or {"labels": [], "predictions": []}


def _ensure_page_persisted(
    library_root: str,
    doc_id: str,
    page: int,
    image_path: str | None = None,
) -> dict[str, Any]:
    """DB hit or FT→persist. Returns labels, predictions, and meta flags."""
    existing = _load_page_from_db(library_root, doc_id, page)
    if existing is not None:
        return {
            "labels": existing["labels"],
            "predictions": existing["predictions"],
            "already_existed": True,
            "labels_written": 0,
            "predictions_written": 0,
            "error": None,
        }

    detected = _cached_detect(library_root, doc_id, page)
    if detected is None:
        return {
            "labels": [],
            "predictions": [],
            "already_existed": False,
            "labels_written": 0,
            "predictions_written": 0,
            "error": "detection unavailable or document not found",
        }

    stored = _persist_page(
        library_root,
        doc_id,
        page,
        detected["labels"],
        detected["predictions"],
        image_path=image_path,
    )
    return {
        "labels": stored["labels"],
        "predictions": stored["predictions"],
        "already_existed": False,
        "labels_written": len(stored["labels"]),
        "predictions_written": len(stored["predictions"]),
        "error": None,
    }


def _get_or_persist_page(
    library_root: str, doc_id: str, page: int
) -> dict[str, list[dict[str, Any]]]:
    result = _ensure_page_persisted(library_root, doc_id, page)
    return {
        "labels": result["labels"],
        "predictions": result["predictions"],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/figure-labels")
async def get_figure_labels(body: dict) -> dict:
    """Return FigureLabel[] for a (doc, page); persist FT on cold miss."""
    library_root, doc_id, page = _parse_page_body(body)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: _get_or_persist_page(library_root, doc_id, page)
    )
    return {"labels": result["labels"]}


@router.post("/predictions")
async def get_coref_predictions(body: dict) -> dict:
    """Return CorefPrediction[] for a (doc, page); persist FT on cold miss."""
    library_root, doc_id, page = _parse_page_body(body)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, lambda: _get_or_persist_page(library_root, doc_id, page)
    )
    return {"predictions": result["predictions"]}


@router.post("/ensure-for-image")
async def ensure_coref_for_image(body: dict) -> dict:
    """Ensure coref rows exist for (doc, page); write-on-miss FT detect."""
    library_root = body.get("libraryRoot") or body.get("library_root") or ""
    doc_id = body.get("docId") or body.get("doc_id") or ""
    page = body.get("page")
    image_path = body.get("imagePath") or body.get("image_path")
    if not library_root or not doc_id or not isinstance(page, int):
        raise ValidationError("libraryRoot, docId, and integer page are required")

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: _ensure_page_persisted(library_root, doc_id, page, image_path),
    )
    return {
        "doc_id": doc_id,
        "page": page,
        "already_existed": result["already_existed"],
        "labels_written": result["labels_written"],
        "predictions_written": result["predictions_written"],
        "error": result["error"],
    }


@router.post("/confirm-prediction")
async def confirm_coref_prediction(body: dict) -> dict:
    """Toggle is_confirmed on a persisted coref_predictions row."""
    library_root = body.get("libraryRoot") or body.get("library_root") or ""
    prediction_id = body.get("predictionId")
    if prediction_id is None:
        prediction_id = body.get("prediction_id")
    is_confirmed = body.get("isConfirmed")
    if is_confirmed is None:
        is_confirmed = body.get("is_confirmed")

    if not library_root or prediction_id is None or is_confirmed is None:
        raise ValidationError(
            "libraryRoot, predictionId, and isConfirmed are required"
        )

    db = DatabaseManager.get(library_root)
    db.initialize()
    with db.kb_conn() as conn:
        cur = conn.execute(
            "UPDATE coref_predictions SET is_confirmed = ? WHERE id = ?",
            (1 if is_confirmed else 0, int(prediction_id)),
        )
        if cur.rowcount == 0:
            raise ValidationError(f"prediction id {prediction_id} not found")
    return {"success": True, "id": int(prediction_id), "is_confirmed": bool(is_confirmed)}


@router.post("/update-pair")
async def update_coref_pair(body: dict) -> int:
    """Replace a prediction with a manual pair; return new row id."""
    library_root = body.get("libraryRoot") or body.get("library_root") or ""
    doc_id = body.get("docId") or body.get("doc_id") or ""
    page = body.get("page")
    old_prediction_id = body.get("oldPredictionId")
    if old_prediction_id is None:
        old_prediction_id = body.get("old_prediction_id")
    mol_smiles = body.get("molSmiles")
    if mol_smiles is None:
        mol_smiles = body.get("mol_smiles")
    mol_bbox = body.get("molBbox")
    if mol_bbox is None:
        mol_bbox = body.get("mol_bbox")
    label_id = body.get("labelId")
    if label_id is None:
        label_id = body.get("label_id")

    if not library_root or not doc_id or not isinstance(page, int) or label_id is None:
        raise ValidationError(
            "libraryRoot, docId, page, and labelId are required"
        )

    db = DatabaseManager.get(library_root)
    db.initialize()
    with db.kb_conn() as conn:
        label_row = conn.execute(
            "SELECT * FROM figure_labels WHERE id = ?",
            (int(label_id),),
        ).fetchone()
        if label_row is None:
            raise ValidationError(f"label id {label_id} not found")

        if old_prediction_id is not None:
            conn.execute(
                "DELETE FROM coref_predictions WHERE id = ?",
                (int(old_prediction_id),),
            )

        smiles_key = mol_smiles or ""
        cur = conn.execute(
            """
            INSERT INTO coref_predictions
                (doc_id, page, mol_smiles, mol_bbox, mol_conf,
                 label_id, label_text, label_bbox, confidence,
                 source, is_confirmed, image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                page,
                smiles_key,
                _bbox_to_text(mol_bbox),
                None,
                int(label_id),
                label_row["label_text"],
                label_row["label_bbox"],
                1.0,
                "manual",
                1,
                label_row["image_path"],
            ),
        )
        new_id = int(cur.lastrowid)
    return new_id


@router.post("/molecule-chain")
async def get_molecule_coref_chain(body: dict) -> dict:
    """Cross-page occurrences for one molecule id / smiles."""
    library_root = body.get("libraryRoot") or body.get("library_root") or ""
    mol_id = body.get("molId") or body.get("mol_id") or ""
    if not library_root or not mol_id:
        raise ValidationError("libraryRoot and molId are required")

    db = DatabaseManager.get(library_root)
    db.initialize()
    occurrences: list[dict[str, Any]] = []
    aliases: list[str] = []
    with db.kb_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM coref_predictions
            WHERE mol_smiles = ? OR label_text = ?
            ORDER BY doc_id, page, id
            """,
            (mol_id, mol_id),
        ).fetchall()
        for r in rows:
            bbox = _bbox_from_text(r["mol_bbox"]) or _bbox_from_text(r["label_bbox"]) or [0, 0, 0, 0]
            smiles = r["mol_smiles"] or ""
            occurrences.append(
                {
                    "doc_id": r["doc_id"],
                    "page": int(r["page"]),
                    "bbox": bbox,
                    "context": r["label_text"] or "",
                    "confidence": float(r["confidence"] or 0.0),
                    "smiles": smiles,
                    "esmiles": smiles,
                }
            )
            if r["label_text"] and r["label_text"] not in aliases:
                aliases.append(r["label_text"])
    return {
        "mol_id": mol_id,
        "occurrences": occurrences,
        "aliases": aliases,
    }


@router.post("/page-parse-result")
async def get_page_parse_result(body: dict) -> dict:
    """Structured page view: molecules from detection cache + coref labels.

    ``pageHPts`` accepted for FE contract; coordinate flip left to FE when
    consuming cached text. Findings empty until heuristic extractor lands.
    """
    library_root, doc_id, page = _parse_page_body(body)
    # pageHPts optional; reserved for future text-line flip
    _ = body.get("pageHPts") or body.get("page_h_pts")

    loop = asyncio.get_running_loop()
    coref = await loop.run_in_executor(
        None, lambda: _get_or_persist_page(library_root, doc_id, page)
    )

    molecules: list[dict[str, Any]] = []
    try:
        db = DatabaseManager.get(library_root)
        db.initialize()
        with db.mol_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM molecule_detections WHERE doc_id = ? AND page = ?",
                (doc_id, page),
            ).fetchall()
        for row in rows:
            molecules.append(dict(row))
    except Exception as e:  # noqa: BLE001 - cache miss is fine
        logger.debug("page-parse detections miss: %s", e)

    structured_text: list[dict[str, Any]] = []
    try:
        from ..core.artifact import ArtifactResolver

        page_path = ArtifactResolver(library_root).page_text(doc_id, page)
        if page_path.is_file():
            text = page_path.read_text(encoding="utf-8", errors="replace")
            if text.strip():
                structured_text.append(
                    {
                        "kind": "paragraph",
                        "content": text,
                        "bbox": [0.0, 0.0, 1.0, 1.0],
                    }
                )
    except Exception as e:  # noqa: BLE001
        logger.debug("page text unavailable: %s", e)

    return {
        "page": page,
        "structured_text": structured_text,
        "molecules": molecules,
        "findings": [],
        "labels": coref["labels"],
        "predictions": coref["predictions"],
    }
