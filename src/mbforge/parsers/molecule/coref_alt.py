"""coref via MolDetv2-FT joint detector.

Single-model inference: MolDetv2-FT outputs molecule bboxes and coref
identifier bboxes in one pass. No OCR step needed (the FT model is
trained on identifier detection directly). Outputs `CorefResult` which
is consumed by `/api/v1/moldet/extract-pdf-page` and `coref_to_rust_dict`
for the vlm_chem.rs Rust frontend bridge.

Replaces the 2026-07-07 implementation: moldet (Doc detector) + RapidOCR
with heuristic identifier filtering. The OCR path was slower and noisier
on identifier text (e.g., "Ia" vs "1a"). The FT model is the canonical
path; OCR-based code has been removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PIL import Image

from mbforge.utils.logger import get_logger

logger = get_logger(__name__)


# ---- 数据类型（moldet_coref 移除后唯一来源） ----


@dataclass
class CorefBbox:
    category_id: int  # 1=分子, 3=标识符
    # Bounding box in **image-relative normalized coordinates**:
    # `[x1, y1, x2, y2]` with values in `[0, 1]`, **top-left origin**
    # (y grows downward, image-processing convention).
    #
    # This is the contract expected by:
    # - `vlm_chem::coref_to_molecules` (Rust) — converts to PDF points
    # - KB `figure_labels.label_bbox` / `coref_predictions.{mol,label}_bbox`
    #   — frontend `projectFigureBboxToPage` projects to PDF page coords
    #
    # Internal pipeline (moldet + RapidOCR) returns pixel coords; the
    # conversion to normalized happens in `detect_coref_via_moldet_ocr`
    # at construction time.
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
    W: int,
    H: int,
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> list[tuple[int, int]]:
    """几何配对：归一化距离 + 水平权重 + 置信度优先。

    所有 bbox 都是 image-relative 归一化 [0,1] 坐标（top-left origin），
    中心点距离直接用归一化单位计算，不再除以 page_width/page_height。
    阈值（0.3 页面比例、水平权重 3、垂直权重 2）按"归一化页面比例"理解。

    额外约束：idt bbox 必须**不与 mol bbox 重叠**（IoU 必须为 0），
    过滤掉分子结构内部的元素符号。
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



# ---- Rust 侧 JSON 序列化（vlm_chem.rs 期望格式） ----


def coref_to_rust_dict(result: CorefResult) -> dict[str, Any]:
    """把 CorefResult 序列化为 vlm_chem.rs 期望的 JSON 结构.

    Rust 侧（vlm_chem.rs:detect_coref）解析:
      bboxes[*]: {category_id, bbox[4], smiles?, molfile?, text?, score}
      corefs[*]: [mol_idx, idt_idx]  (嵌套数组)
    """
    return {
        "bboxes": [
            {
                "category_id": b.category_id,
                "bbox": list(b.bbox),
                "smiles": b.smiles,
                "molfile": None,
                "text": b.text,
                "score": b.score,
            }
            for b in result.bboxes
        ],
        "corefs": [list(pair) for pair in result.corefs],
    }


# ---- MolDetv2-FT 联合检测（分子 + coref 一次推理） ----

_ft_detector_singleton: Any | None = None


def get_moldet_ft() -> Any:
    """获取全局 MolDetv2-FT 检测器单例。"""
    global _ft_detector_singleton
    if _ft_detector_singleton is None:
        try:
            from mbforge.backends.moldet_v2_ft import get_moldet_ft as _get
            _ft_detector_singleton = _get()
        except Exception as e:
            logger.warning("MolDetv2-FT 加载失败: %s", e)
            _ft_detector_singleton = None
    return _ft_detector_singleton


def detect_coref_via_ft_detector(
    image: Image.Image,
    ft_detector: Any = None,
    page_width: float = 595.0,
    page_height: float = 842.0,
    mol_conf_threshold: float = 0.3,
    idt_conf_threshold: float = 0.3,
) -> CorefResult:
    """使用 MolDetv2-FT 联合检测器实现 coref 配对。

    该检测器一次推理同时输出分子和标识符 bbox，无需单独的 OCR 步骤。

    Args:
        image: PIL 图像
        ft_detector: `MolDetv2FTDetector` 实例。None 时使用全局单例
        page_width: PDF 页面宽度（点）
        page_height: PDF 页面高度（点）
        mol_conf_threshold: 分子检测置信度阈值
        idt_conf_threshold: 标识符检测置信度阈值

    Returns:
        `CorefResult` — 与 `detect_coref_via_moldet_ocr` 输出格式一致。
    """
    from mbforge.backends.moldet_v2_ft import MolDetv2FTDetector

    if ft_detector is None:
        ft_detector = get_moldet_ft()
    if ft_detector is None or not isinstance(ft_detector, MolDetv2FTDetector):
        logger.warning("MolDetv2-FT 不可用，跳过联合检测")
        return CorefResult(bboxes=[], corefs=[])

    if not ft_detector.is_available():
        logger.warning("MolDetv2-FT 模型未加载，跳过联合检测")
        return CorefResult(bboxes=[], corefs=[])

    W, H = image.size
    inv_w = 1.0 / W if W > 0 else 0.0
    inv_h = 1.0 / H if H > 0 else 0.0

    def _to_norm(
        box: tuple[float, float, float, float],
    ) -> tuple[float, float, float, float]:
        """Pixel bbox → 归一化 bbox [0,1]。"""
        x1, y1, x2, y2 = box
        nx1 = max(0.0, min(1.0, x1 * inv_w))
        ny1 = max(0.0, min(1.0, y1 * inv_h))
        nx2 = max(0.0, min(1.0, x2 * inv_w))
        ny2 = max(0.0, min(1.0, y2 * inv_h))
        return (nx1, ny1, nx2, ny2)

    # 1. 联合检测（一次推理同时得到分子和标识符）
    all_boxes = ft_detector.detect(image)

    bboxes: list[CorefBbox] = []
    mol_indices: list[int] = []
    idt_indices: list[int] = []

    # 2. 分离分子和标识符 bbox
    for x1, y1, x2, y2, conf, category_id in all_boxes:
        if category_id == 1 and conf >= mol_conf_threshold:
            # 分子 bbox
            bboxes.append(
                CorefBbox(category_id=1, bbox=_to_norm((x1, y1, x2, y2)), score=conf)
            )
            mol_indices.append(len(bboxes) - 1)
        elif category_id == 3 and conf >= idt_conf_threshold:
            # 标识符 bbox
            bboxes.append(
                CorefBbox(
                    category_id=3,
                    bbox=_to_norm((x1, y1, x2, y2)),
                    text="",  # FT 模型不输出文本，需要后续 OCR
                    score=conf,
                )
            )
            idt_indices.append(len(bboxes) - 1)

    # 3. 几何配对
    corefs = _pair_corefs(
        bboxes, mol_indices, idt_indices, W, H, page_width, page_height
    )

    logger.info(
        "coref_ft: mols=%d, idts=%d, pairs=%d",
        len(mol_indices),
        len(idt_indices),
        len(corefs),
    )
    return CorefResult(bboxes=bboxes, corefs=corefs)
