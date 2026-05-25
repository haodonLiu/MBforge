"""pdfplumber ROI 文本提取器.

在 MolDetv2 检测到的分子区域附近提取文本上下文（caption、段落、标签），
回填到 ExtractionResult.context_text 供人工确认和关联引擎使用。

坐标系说明：
- PDF 坐标（fitz）：左下角原点，(x1, y1, x2, y2)
- pdfplumber 坐标：左上角原点，(x0, top, x1, bottom)
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore

from mbforge.utils.logger import get_logger

logger = get_logger(__name__)


def pdf_to_pdfplumber_bbox(
    bbox_pdf: Tuple[float, float, float, float],
    page_h_pts: float,
) -> Tuple[float, float, float, float]:
    """PDF 坐标 → pdfplumber 坐标.

    Args:
        bbox_pdf: (x1, y1, x2, y2)，左下角原点
        page_h_pts: PDF 页面高度（点单位）

    Returns:
        (x0, top, x1, bottom)，pdfplumber 坐标（左上角原点）
    """
    x1_pdf, y1_pdf, x2_pdf, y2_pdf = bbox_pdf
    x0 = x1_pdf
    x1 = x2_pdf
    top = page_h_pts - y2_pdf
    bottom = page_h_pts - y1_pdf
    return (x0, top, x1, bottom)


class ROITextExtractor:
    """在分子结构 bbox 附近提取文本上下文."""

    def __init__(
        self,
        top_margin: float = 20.0,
        bottom_margin: float = 20.0,
        side_margin: float = 10.0,
        max_chars: int = 500,
    ) -> None:
        """初始化提取器.

        Args:
            top_margin: 向上扩展的距离（点）
            bottom_margin: 向下扩展的距离（点）
            side_margin: 左右扩展的距离（点）
            max_chars: 返回文本的最大字符数
        """
        self.top_margin = top_margin
        self.bottom_margin = bottom_margin
        self.side_margin = side_margin
        self.max_chars = max_chars

    def extract_context(
        self,
        pdf_path: Path,
        page_idx: int,
        bbox_pdf: Tuple[float, float, float, float],
        page_w_pts: float,
        page_h_pts: float,
    ) -> str:
        """提取 bbox 附近的文本上下文.

        搜索策略：
        1. 先尝试 bbox 正上方（通常是 caption）
        2. 再尝试 bbox 正下方
        3. 最后尝试 bbox 内部（可能包含标签）
        4. 合并去重后截取前 max_chars 字符

        Args:
            pdf_path: PDF 文件路径
            page_idx: 页码（从 0 开始）
            bbox_pdf: PDF 坐标系中的 bbox
            page_w_pts: 页面宽度
            page_h_pts: 页面高度

        Returns:
            提取到的文本上下文
        """
        if pdfplumber is None:
            logger.warning("pdfplumber 未安装，跳过 ROI 文本提取")
            return ""

        texts: List[str] = []
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                if page_idx >= len(pdf.pages):
                    return ""
                page = pdf.pages[page_idx]

                # 1. 上方区域（caption 最常见位置）
                top_roi = self._expand_bbox(
                    bbox_pdf, page_w_pts, page_h_pts, direction="top"
                )
                top_text = self._extract_within_bbox(page, top_roi, page_h_pts)
                if top_text:
                    texts.append(top_text)

                # 2. 下方区域
                bottom_roi = self._expand_bbox(
                    bbox_pdf, page_w_pts, page_h_pts, direction="bottom"
                )
                bottom_text = self._extract_within_bbox(
                    page, bottom_roi, page_h_pts
                )
                if bottom_text and bottom_text != top_text:
                    texts.append(bottom_text)

                # 3. bbox 内部（可能包含化学名称标签）
                inner_text = self._extract_within_bbox(
                    page, bbox_pdf, page_h_pts
                )
                if inner_text and inner_text not in texts:
                    texts.append(inner_text)

        except Exception as exc:
            logger.warning("ROI 文本提取失败 (page=%d): %s", page_idx, exc)

        context = " | ".join(texts)
        if len(context) > self.max_chars:
            context = context[: self.max_chars] + "..."
        return context

    def _expand_bbox(
        self,
        bbox_pdf: Tuple[float, float, float, float],
        page_w_pts: float,
        page_h_pts: float,
        direction: str = "top",
    ) -> Tuple[float, float, float, float]:
        """按方向扩展 bbox.

        Args:
            bbox_pdf: 原始 bbox
            page_w_pts: 页面宽度（用于裁剪边界）
            page_h_pts: 页面高度（用于裁剪边界）
            direction: 'top' | 'bottom' | 'both'

        Returns:
            扩展后的 bbox（仍使用 PDF 左下角原点坐标系）
        """
        x1, y1, x2, y2 = bbox_pdf

        if direction == "top":
            # 向上扩展（y2 增大）
            new_y2 = min(page_h_pts, y2 + self.top_margin)
            new_y1 = y1  # 保持下边界不变，缩小范围更聚焦
            return (x1, y1, x2, new_y2)
        elif direction == "bottom":
            # 向下扩展（y1 减小）
            new_y1 = max(0.0, y1 - self.bottom_margin)
            return (x1, new_y1, x2, y2)
        elif direction == "both":
            new_y1 = max(0.0, y1 - self.bottom_margin)
            new_y2 = min(page_h_pts, y2 + self.top_margin)
            new_x1 = max(0.0, x1 - self.side_margin)
            new_x2 = min(page_w_pts, x2 + self.side_margin)
            return (new_x1, new_y1, new_x2, new_y2)
        else:
            return bbox_pdf

    def _extract_within_bbox(
        self,
        page: "pdfplumber.page.Page",  # type: ignore[name-defined]
        bbox_pdf: Tuple[float, float, float, float],
        page_h_pts: float,
    ) -> str:
        """在指定 PDF bbox 内提取文本.

        Args:
            page: pdfplumber Page 对象
            bbox_pdf: PDF 坐标系 bbox
            page_h_pts: 页面高度

        Returns:
            提取到的文本（已 strip）
        """
        pp_bbox = pdf_to_pdfplumber_bbox(bbox_pdf, page_h_pts)
        try:
            cropped = page.within_bbox(pp_bbox)
            text = cropped.extract_text() or ""
            return text.strip()
        except Exception:
            return ""
