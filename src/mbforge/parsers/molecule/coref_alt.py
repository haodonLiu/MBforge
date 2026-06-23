"""coref via moldet + RapidOCR — 替代 pix2seq-based coref 的轻量实现。

复用 `mbforge.backends.moldet.MolDetv2DocDetector` + `_RapidOCRAdapter`，
无新模型依赖，无 vendor 代码（thomas0809/RxnScribe）。

输出 `CorefResult` 与 `MolDetectCorefBackend.detect_coref` 完全兼容，
可直接平替上游调用方（`server.py:457` HTTP endpoint、`vlm_chem.rs`）。

权衡：
- 不再需要 `coref_best.ckpt`（412 MB）和 `molcoref/` 17 个 vendor 文件
- 标识符检测从训练模型 → 启发式过滤（精度略降，速度显著提升）
- 配对逻辑一致：归一化距离 + 水平权重 + 置信度优先
"""

from __future__ import annotations

import re
from typing import Any

from PIL import Image

from mbforge.backends.moldet_coref import CorefBbox, CorefResult
from mbforge.utils.logger import get_logger

logger = get_logger(__name__)

# 段落文本特征词（不应作为 identifier）
_COMMON_WORDS: frozenset[str] = frozenset({
    "the", "of", "and", "or", "a", "an", "to", "in", "for", "is", "are",
    "with", "by", "as", "on", "at", "from", "this", "that", "be", "or",
    "an", "or", "formula", "compound", "salt", "pharmaceutically",
    "acceptable", "some", "embodiments", "structure", "has",
})

# identifier 字符约束：首字符为字母或左括号，后续字母/数字/常见化学符号
_IDT_CHARS = re.compile(r"^[\(]?[A-Za-z][A-Za-z0-9¹²³⁴⁵⁶⁷⁸⁹⁰\-\)]*[\),]?$")


def _is_identifier_candidate(text: str) -> bool:
    """启发式：判断 OCR 文本是否像化学标识符（Ia/Ib/(Ia)/Y/NH/A1/A2 等）。"""
    if not text:
        return False
    t = text.strip().strip(".,;:")
    if not t or len(t) > 10:
        return False
    if " " in t:  # 含空格 → 段落文本
        return False
    if t.lower().rstrip("().,") in _COMMON_WORDS:
        return False
    if not re.search(r"[A-Za-z]", t):
        return False
    if not _IDT_CHARS.match(t):
        return False
    return True


def _normalize_idt(text: str) -> str:
    """清洗 OCR 误识：小写 l/I 互换，1/l/! 修正。"""
    t = text.strip()
    # 形似修正（保守）：首字符 I↔l 视上下文；这里只修末尾的常见误识
    if t.endswith("1b)") or t.endswith("lb)"):
        t = t[:-3] + "Ib)"
    return t


def _pair_corefs(
    bboxes: list[CorefBbox],
    mol_indices: list[int],
    idt_indices: list[int],
    W: int,
    H: int,
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> list[tuple[int, int]]:
    """几何配对：归一化距离 + 水平权重 + 置信度优先（与 data.py:_pair_corefs 一致）。

    额外约束：idt bbox 必须**不与 mol bbox 重叠**（IoU == 0），
    过滤掉分子结构内部的元素符号（O/N/Y/H/C）。
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
            dx = (mx - ix) / page_width
            dy = (my - iy) / page_height
            # 任一轴超 30% 页面即视为太远（formula label 不会离分子这么远）
            if abs(dx) > 0.3 or abs(dy) > 0.3:
                continue
            # 约束：idt bbox 不在 mol bbox 内部（IoU 必须为 0）
            if _bbox_iou(bboxes[idt_i].bbox, bboxes[mi].bbox) > 0:
                continue
            h_dist = abs(mx - ix) / page_width
            v_dist = abs(my - iy) / page_height
            score = 1.0 / (1.0 + h_dist * 3 + v_dist * 2)
            if score > best_score:
                best_score = score
                best_mol = mi
        if best_mol >= 0:
            pairs.append((best_mol, idt_i))
            used_mols.add(best_mol)
    return pairs


def _bbox_iou(a: tuple, b: tuple) -> float:
    """两个像素 bbox 的 IoU。"""
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


def _is_inside(inner: tuple, outer: tuple) -> bool:
    """检查 inner bbox 是否完全在 outer bbox 内。"""
    ix1, iy1, ix2, iy2 = inner
    ox1, oy1, ox2, oy2 = outer
    return ox1 <= ix1 and oy1 <= iy1 and ix2 <= ox2 and iy2 <= oy2


def _contain_ratio(inner: tuple, outer: tuple) -> float:
    """inner bbox 面积有多大比例在 outer 内。"""
    ix1, iy1, ix2, iy2 = inner
    ox1, oy1, ox2, oy2 = outer
    # intersection
    cx1, cy1 = max(ix1, ox1), max(iy1, oy1)
    cx2, cy2 = min(ix2, ox2), min(iy2, oy2)
    if cx2 <= cx1 or cy2 <= cy1:
        return 0.0
    inter = (cx2 - cx1) * (cy2 - cy1)
    area_inner = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    return inter / area_inner if area_inner > 0 else 0.0


def detect_coref_via_moldet_ocr(
    image: Image.Image,
    doc_detector: Any,
    ocr_adapter: Any,
    page_width: float = 595.0,
    page_height: float = 842.0,
    mol_conf_threshold: float = 0.25,
) -> CorefResult:
    """moldet + RapidOCR 实现 coref 配对。

    Args:
        image: PIL 图像
        doc_detector: `MolDetv2DocDetector` 实例
        ocr_adapter: `_RapidOCRAdapter` 实例
        page_width: PDF 页面宽度（点）
        page_height: PDF 页面高度（点）
        mol_conf_threshold: moldet 置信度阈值（默认 0.25，比默认 0.4 宽松以提高召回）

    Returns:
        `CorefResult` — 与 `MolDetectCorefBackend.detect_coref` 输出一致。
    """
    W, H = image.size

    # 1. moldet 检测分子（像素坐标）
    mol_results = doc_detector.detect(image)  # [(x1,y1,x2,y2,conf), ...]

    # 2. RapidOCR 全图
    ocr_results = ocr_adapter.readtext(image, detail=1)  # [(box_4pts, text, score), ...]

    bboxes: list[CorefBbox] = []
    mol_indices: list[int] = []

    # 3. 加 Mol bbox
    for x1, y1, x2, y2, conf in mol_results:
        if conf < mol_conf_threshold:
            continue
        bboxes.append(CorefBbox(category_id=1, bbox=(x1, y1, x2, y2), score=conf))
        mol_indices.append(len(bboxes) - 1)

    # 4. 加 Idt bbox（OCR 候选 + 启发式过滤）
    idt_indices: list[int] = []
    for box_pts, text, ocr_conf in ocr_results or []:
        if not _is_identifier_candidate(text):
            continue
        xs = [p[0] for p in box_pts]
        ys = [p[1] for p in box_pts]
        idt_bbox = (min(xs), min(ys), max(xs), max(ys))
        # 过滤：idt 50%+ 面积在某个 mol 内部 → 视为分子结构内部元素（非 label）
        if any(_contain_ratio(idt_bbox, bboxes[mi].bbox) > 0.5 for mi in mol_indices):
            continue
        bboxes.append(
            CorefBbox(
                category_id=3,
                bbox=idt_bbox,
                text=_normalize_idt(text),
                score=ocr_conf,
            )
        )
        idt_indices.append(len(bboxes) - 1)

    # 5. 几何配对
    corefs = _pair_corefs(bboxes, mol_indices, idt_indices, W, H, page_width, page_height)

    logger.info(
        "coref_alt: mols=%d, idts=%d, pairs=%d",
        len(mol_indices), len(idt_indices), len(corefs),
    )
    return CorefResult(bboxes=bboxes, corefs=corefs)
