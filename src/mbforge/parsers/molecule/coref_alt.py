"""coref via MolDetv2-FT joint detector.

Single-model inference: MolDetv2-FT outputs molecule bboxes and coref
identifier bboxes in one pass. Identifier crops are then OCR'd by
`RapidOCRCropAdapter` so downstream consumers receive real label text.
Outputs `CorefResult` which is consumed by
`routers/moldet_api.py:extract_pdf_page` and
`routers/coref.py:_coref_to_kb_shapes`.

Replaces the 2026-07-07 implementation: moldet (Doc detector) + RapidOCR
with heuristic identifier filtering. The FT model is the canonical
detection path; the OCR step is now limited to the small identifier
crops produced by the FT model.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from PIL import Image

from mbforge.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CorefBbox:
    category_id: int  # 1=分子, 3=标识符
    # Bounding box in **image-relative normalized coordinates**:
    # `[x1, y1, x2, y2]` with values in `[0, 1]`, **top-left origin**
    # (y grows downward, image-processing convention).
    #
    # Consumers:
    # - KB `figure_labels.label_bbox` / `coref_predictions.{mol,label}_bbox`
    #   — frontend `projectFigureBboxToPage` projects to PDF page coords
    #
    # Conversion from pixel coords to normalized happens at FT-detection
    # construction time (see `detect_coref_via_ft_detector`).
    bbox: tuple[float, float, float, float]
    smiles: str | None = None
    text: str | None = None
    score: float = 0.0


@dataclass
class CorefResult:
    bboxes: list[CorefBbox]
    corefs: list[tuple[int, int]]  # [(mol_idx, idt_idx), ...]



def _pair_corefs(
    bboxes: list[CorefBbox],
    mol_indices: list[int],
    idt_indices: list[int],
    width: int,
    height: int,
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> list[tuple[int, int]]:
    """Geometric pairing: normalized distance + horizontal bias + score priority.

    All bboxes are image-relative normalized [0, 1] coordinates (top-left
    origin). Center distances are computed directly in normalized units;
    ``page_width`` and ``page_height`` are kept for API compatibility but
    are no longer used as divisors.

    Thresholds (0.3 page fraction, horizontal weight 3, vertical weight 2)
    are interpreted as normalized page fractions.

    Additional constraint: identifier bboxes must not overlap molecule
    bboxes (IoU must be 0) so element symbols inside a structure are not
    mistaken for labels.
    """
    if not mol_indices or not idt_indices:
        return []

    centers: list[tuple[float, float]] = []
    for b in bboxes:
        x1, y1, x2, y2 = b.bbox
        centers.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0))

    sorted_idts = sorted(
        idt_indices,
        key=lambda i: bboxes[i].score,
        reverse=True,
    )

    pairs: list[tuple[int, int]] = []
    used_mols: set[int] = set()

    for idt_i in sorted_idts:
        ix, iy = centers[idt_i]
        best_mol, best_score = -1, -1.0
        for mi in mol_indices:
            if mi in used_mols:
                continue
            mx, my = centers[mi]
            # 归一化页面比例：0.3 = 30% 页面
            dx = mx - ix
            dy = my - iy
            if abs(dx) > 0.3 or abs(dy) > 0.3:
                continue
            # 约束：idt bbox 不在 mol bbox 内部（IoU 必须为 0）
            if _bbox_iou(bboxes[idt_i].bbox, bboxes[mi].bbox) > 0:
                continue
            h_dist = abs(mx - ix)
            v_dist = abs(my - iy)
            score = 1.0 / (1.0 + h_dist * 3 + v_dist * 2)
            if score > best_score:
                best_score = score
                best_mol = mi
        if best_mol >= 0:
            pairs.append((best_mol, idt_i))
            used_mols.add(best_mol)
    return pairs


def _bbox_iou(a: tuple, b: tuple) -> float:
    """IoU of two image-relative normalized bboxes."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0

# ---- API JSON 序列化（HTTP 端点 /api/v1/moldet/* 的响应载荷） ----


def to_api_dict(result: CorefResult) -> dict[str, Any]:
    """把 CorefResult 序列化为 API 响应 JSON 结构.

    响应形状:
      bboxes[*]: {category_id, bbox[4], smiles?, text?, score}
      corefs[*]: [mol_idx, idt_idx]  (嵌套数组)
    """
    return {
        "bboxes": [
            {
                "category_id": b.category_id,
                "bbox": list(b.bbox),
                "smiles": b.smiles,
                "text": b.text,
                "score": b.score,
            }
            for b in result.bboxes
        ],
        "corefs": [list(pair) for pair in result.corefs],
    }


# ---- MolDetv2-FT 联合检测（分子 + coref 一次推理） ----

_ft_detector_singleton: Any | None = None
_ft_detector_lock = threading.Lock()


def get_moldet_ft() -> Any:
    """获取全局 MolDetv2-FT 检测器单例（线程安全）。"""
    global _ft_detector_singleton
    if _ft_detector_singleton is None:
        with _ft_detector_lock:
            if _ft_detector_singleton is None:
                try:
                    from mbforge.backends.moldet_v2_ft import get_moldet_ft as _get
                    _ft_detector_singleton = _get()
                except Exception as e:
                    logger.warning("MolDetv2-FT 加载失败: %s", e)
                    _ft_detector_singleton = None
    return _ft_detector_singleton


def _ocr_identifier_crops(
    image: Image.Image,
    idt_indices: list[int],
    bboxes: list[CorefBbox],
    padding: float = 0.1,
) -> list[str]:
    """OCR identifier crops and return one text string per identifier bbox.

    The returned list is aligned with ``idt_indices``: ``result[i]`` is the
    OCR text for the identifier at ``bboxes[idt_indices[i]]``. If OCR is
    unavailable or fails, the corresponding entry is an empty string.
    """
    if not idt_indices:
        return []

    try:
        from mbforge.backends.ocr.rapidocr_adapter import RapidOCRCropAdapter
    except Exception as exc:  # noqa: BLE001 - optional dependency
        logger.debug("RapidOCRCropAdapter import failed: %s", exc)
        return [""] * len(idt_indices)

    try:
        adapter = RapidOCRCropAdapter.instance()
    except Exception as exc:  # noqa: BLE001 - adapter init may fail
        logger.debug("RapidOCRCropAdapter unavailable: %s", exc)
        return [""] * len(idt_indices)

    width, height = image.size
    crops: list[Image.Image] = []
    for idx in idt_indices:
        x1, y1, x2, y2 = bboxes[idx].bbox
        bw, bh = x2 - x1, y2 - y1
        pad_w, pad_h = bw * padding, bh * padding
        px1 = max(0, int((x1 - pad_w) * width))
        py1 = max(0, int((y1 - pad_h) * height))
        px2 = min(width, int((x2 + pad_w) * width))
        py2 = min(height, int((y2 + pad_h) * height))
        if px2 <= px1 or py2 <= py1:
            crops.append(Image.new("RGB", (1, 1), (255, 255, 255)))
            continue
        crops.append(image.crop((px1, py1, px2, py2)).convert("RGB"))

    try:
        return adapter.readtext_batch(crops, max_workers=4)
    except Exception as exc:  # noqa: BLE001 - inference can fail on weird crops
        logger.warning("Identifier batch OCR failed: %s", exc)
        return [""] * len(idt_indices)


def detect_coref_via_ft_detector(
    image: Image.Image,
    ft_detector: Any = None,
    page_width: float = 595.0,
    page_height: float = 842.0,
    mol_conf_threshold: float = 0.3,
    idt_conf_threshold: float = 0.3,
    use_ocr: bool = True,
) -> CorefResult:
    """Detect molecules + coref identifiers and pair them geometrically.

    The FT detector emits molecule bboxes (category_id=1) and identifier
    bboxes (category_id=3) in a single inference. Identifier crops are then
    OCR'd so that ``CorefBbox.text`` contains real label text when possible.

    Args:
        image: PIL image.
        ft_detector: ``MolDetv2FTDetector`` instance, or ``None`` to use the
            global singleton.
        page_width: PDF page width in points. Kept for API compatibility;
            ``_pair_corefs`` works in image-relative normalized units.
        page_height: PDF page height in points. Kept for API compatibility.
        mol_conf_threshold: Molecule confidence threshold applied after model
            inference. Note that the detector's own ``conf_threshold``
            (default 0.5) gates boxes before they reach this filter, so
            thresholds below 0.5 only take effect if the detector was created
            with a lower ``conf_threshold``.
        idt_conf_threshold: Identifier confidence threshold. Same note as
            ``mol_conf_threshold`` applies.
        use_ocr: If ``True`` (default), run RapidOCR on identifier crops to
            fill ``CorefBbox.text``. Disable in tests or when the caller will
            OCR labels itself.

    Returns:
        ``CorefResult`` matching the shape consumed by ``moldet_api.py`` and
        ``routers/coref.py``.
    """
    from mbforge.backends.moldet_v2_ft import MolDetv2FTDetector

    if ft_detector is None:
        ft_detector = get_moldet_ft()
    if ft_detector is None or not isinstance(ft_detector, MolDetv2FTDetector):
        logger.warning("MolDetv2-FT unavailable, skipping joint detection")
        return CorefResult(bboxes=[], corefs=[])

    if not ft_detector.is_available():
        logger.warning("MolDetv2-FT model not loaded, skipping joint detection")
        return CorefResult(bboxes=[], corefs=[])

    width, height = image.size
    inv_w = 1.0 / width if width > 0 else 0.0
    inv_h = 1.0 / height if height > 0 else 0.0

    def _to_norm(
        box: tuple[float, float, float, float],
    ) -> tuple[float, float, float, float]:
        """Pixel bbox -> normalized bbox [0, 1]."""
        x1, y1, x2, y2 = box
        nx1 = max(0.0, min(1.0, x1 * inv_w))
        ny1 = max(0.0, min(1.0, y1 * inv_h))
        nx2 = max(0.0, min(1.0, x2 * inv_w))
        ny2 = max(0.0, min(1.0, y2 * inv_h))
        return (nx1, ny1, nx2, ny2)

    # 1. Joint detection: one inference returns both molecules and identifiers.
    all_boxes = ft_detector.detect(image)

    bboxes: list[CorefBbox] = []
    mol_indices: list[int] = []
    idt_indices: list[int] = []

    # 2. Separate molecule and identifier bboxes.
    for x1, y1, x2, y2, conf, category_id in all_boxes:
        if category_id == 1 and conf >= mol_conf_threshold:
            bboxes.append(
                CorefBbox(category_id=1, bbox=_to_norm((x1, y1, x2, y2)), score=conf)
            )
            mol_indices.append(len(bboxes) - 1)
        elif category_id == 3 and conf >= idt_conf_threshold:
            bboxes.append(
                CorefBbox(
                    category_id=3,
                    bbox=_to_norm((x1, y1, x2, y2)),
                    text="",  # Filled by OCR below.
                    score=conf,
                )
            )
            idt_indices.append(len(bboxes) - 1)

    # 3. OCR identifier crops to obtain real label text.
    if use_ocr and idt_indices:
        ocr_texts = _ocr_identifier_crops(image, idt_indices, bboxes)
        for idx, idt_i in enumerate(idt_indices):
            bboxes[idt_i].text = ocr_texts[idx]

    # 4. Geometric pairing.
    corefs = _pair_corefs(
        bboxes, mol_indices, idt_indices, width, height, page_width, page_height
    )

    logger.info(
        "coref_ft: mols=%d, idts=%d, pairs=%d",
        len(mol_indices),
        len(idt_indices),
        len(corefs),
    )
    return CorefResult(bboxes=bboxes, corefs=corefs)
