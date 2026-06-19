"""rxnscribe.data — MolDetect 自定义 coref 后处理实现。

上游 thomas0809/RxnScribe 的 data.py 包含 `postprocess_reactions`（处理反应图）。
MolDetect 复用了 pix2seq 模型做分子-标识符 coref，但**不包含** `postprocess_coref_results`。
本文件提供该函数的最小实现：把 BboxTokenizer 解码出的 bboxes 分类、可选跑
molscribe/ocr 补 SMILES/文本、再用最近邻配对得到 coref 关系。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def postprocess_coref_results(
    bboxes: list[dict[str, Any]],
    image_file: str | None = None,
    image: Any = None,
    molscribe: Any = None,
    ocr: Any = None,
    batch_size: int = 32,
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> dict[str, Any]:
    """后处理 pix2seq 序列解码后的 bboxes，得到 coref 关系。

    Args:
        bboxes: BboxTokenizer.sequence_to_data 输出，每个元素：
                ``{"category": "mol"|"sup"|"txt"|"idt", "bbox": (x1,y1,x2,y2),
                "category_id": int, "score": float}``
        image_file / image: 原图。molscribe/ocr 需要从原图 crop。
        molscribe: 可选。``predict_images(pil_images, batch_size=...)`` →
                   ``[{"smiles": str, "molfile": str}, ...]``。
        ocr:      可选。``readtext(pil_image, detail=0)`` → ``[text, ...]``。
        page_width: PDF 页面宽度（点单位），用于归一化距离计算
        page_height: PDF 页面高度（点单位），用于归一化距离计算

    Returns:
        ``{"bboxes": [{category_id, bbox, smiles, molfile, text, score}, ...],
          "corefs": [(mol_idx, idt_idx), ...]}``
    """
    pil_image = _to_pil(image, image_file)
    if pil_image is None:
        return {
            "bboxes": [
                {
                    "category_id": b.get("category_id", 0),
                    "bbox": list(b.get("bbox", (0, 0, 0, 0))),
                    "smiles": None,
                    "molfile": None,
                    "text": None,
                    "score": b.get("score", 0.0),
                }
                for b in bboxes
            ],
            "corefs": [],
        }

    W, H = pil_image.size
    mol_indices: list[int] = []
    idt_indices: list[int] = []
    mol_crops: list[Any] = []
    for i, b in enumerate(bboxes):
        cat = b.get("category", "")
        if cat in ("mol", "sup"):
            mol_indices.append(i)
            mol_crops.append(_crop(pil_image, b.get("bbox", (0, 0, 0, 0)), W, H))
        elif cat in ("txt", "idt"):
            idt_indices.append(i)

    smiles_map: dict[int, str] = {}
    molfile_map: dict[int, str] = {}
    if molscribe and mol_crops:
        try:
            predictions = molscribe.predict_images(mol_crops, batch_size=batch_size)
            for idx, pred in zip(mol_indices, predictions):
                smiles_map[idx] = pred.get("smiles", "") or ""
                molfile_map[idx] = pred.get("molfile", "") or ""
        except Exception as exc:
            logger.warning("molscribe 预测失败（不影响 coref 配对）: %s", exc)

    text_map: dict[int, str] = {}
    if ocr and idt_indices:
        for i in idt_indices:
            crop = _crop(pil_image, bboxes[i].get("bbox", (0, 0, 0, 0)), W, H)
            try:
                results = ocr.readtext(crop, detail=0)
                text_map[i] = " ".join(results).strip() if results else ""
            except Exception as exc:
                logger.warning("ocr 读取失败（id=%d）: %s", i, exc)
                text_map[i] = ""

    out_bboxes: list[dict[str, Any]] = []
    for i, b in enumerate(bboxes):
        out_bboxes.append({
            "category_id": b.get("category_id", 0),
            "bbox": list(b.get("bbox", (0, 0, 0, 0))),
            "smiles": smiles_map.get(i),
            "molfile": molfile_map.get(i),
            "text": text_map.get(i),
            "score": b.get("score", 0.0),
        })

    # 使用增强的配对算法（传入页面尺寸用于归一化）
    corefs = _pair_corefs(bboxes, mol_indices, idt_indices, page_width, page_height)
    return {"bboxes": out_bboxes, "corefs": corefs}


def _to_pil(image: Any, image_file: str | None) -> Any:
    if image is None and image_file is not None:
        try:
            from PIL import Image
            return Image.open(image_file).convert("RGB")
        except Exception as exc:
            logger.warning("加载 image_file 失败: %s", exc)
            return None
    if image is None:
        return None
    try:
        from PIL import Image
        if isinstance(image, Image.Image):
            return image.convert("RGB")
    except Exception:
        return None
    try:
        import numpy as np
        from PIL import Image
        if isinstance(image, np.ndarray):
            return Image.fromarray(image).convert("RGB")
    except Exception:
        return None
    return None


def _crop(pil_image: Any, bbox: tuple, W: int, H: int) -> Any:
    """按 (x1, y1, x2, y2) crop，clip 到图像边界。bbox 无效时返回原图。"""
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(int(x1), W))
    y1 = max(0, min(int(y1), H))
    x2 = max(0, min(int(x2), W))
    y2 = max(0, min(int(y2), H))
    if x2 <= x1 or y2 <= y1:
        return pil_image
    return pil_image.crop((x1, y1, x2, y2))


def _pair_corefs(
    bboxes: list[dict[str, Any]],
    mol_indices: list[int],
    idt_indices: list[int],
    page_width: float = 595.0,
    page_height: float = 842.0,
) -> list[tuple[int, int]]:
    """增强配对：空间关系 + 垂直对齐 + 置信度优先。

    改进点：
    1. 归一化距离计算（考虑页面宽高）
    2. 空间关系评分（水平距离权重更高）
    3. 排除太远的候选（超过页面 30%）
    4. 按置信度排序 idt（高置信度优先配对）
    5. 防止重复配对（每个 mol 最多配对一个 idt）
    """
    if not mol_indices or not idt_indices:
        return []

    # 计算 bbox 中心
    centers: list[tuple[float, float]] = []
    for b in bboxes:
        x1, y1, x2, y2 = b.get("bbox", (0, 0, 0, 0))
        centers.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0))

    # 按置信度排序 idt（高置信度优先配对）
    sorted_idts = sorted(
        idt_indices,
        key=lambda i: bboxes[i].get("score", 0),
        reverse=True
    )

    pairs: list[tuple[int, int]] = []
    used_mols: set[int] = set()

    for idt_i in sorted_idts:
        ix, iy = centers[idt_i]

        # 候选 mol：未使用过的，且在合理距离内
        candidates: list[tuple[int, float]] = []
        for mi in mol_indices:
            if mi in used_mols:
                continue
            mx, my = centers[mi]

            # 归一化距离
            dx = (mx - ix) / page_width
            dy = (my - iy) / page_height

            # 排除太远的（超过页面宽度的 30%）
            if abs(dx) > 0.3 and abs(dy) > 0.3:
                continue

            # 空间关系评分：
            # 1. 水平距离小 → 高分（标号通常在分子旁边）
            # 2. 垂直对齐 → 高分（标号通常在分子下方或右侧）
            h_dist = abs(mx - ix) / page_width
            v_dist = abs(my - iy) / page_height

            # 评分：水平距离权重更高
            score = 1.0 / (1.0 + h_dist * 3 + v_dist * 2)
            candidates.append((mi, score))

        if candidates:
            # 选择得分最高的
            best_mol = max(candidates, key=lambda x: x[1])[0]
            pairs.append((best_mol, idt_i))
            used_mols.add(best_mol)

    return pairs
