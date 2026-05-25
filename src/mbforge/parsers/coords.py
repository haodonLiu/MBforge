"""坐标系映射工具 — PDF / 图像 / 屏幕 三坐标系统一转换.

所有下游模块只认"PDF 页面坐标系"（点单位，左下角原点）。
MolDetv2 输出的图像坐标、pdfplumber 输出的文本坐标、用户框选的屏幕坐标，
必须在此模块中完成转换，禁止分散到各 widget。
"""

from __future__ import annotations


import fitz
from PyQt6.QtCore import QRect


# ---------------------------------------------------------------------------
# 图像坐标 ↔ PDF 坐标
# ---------------------------------------------------------------------------

def scale_from_page_size(
    page_w_pts: float,
    page_h_pts: float,
    image_w: int,
    image_h: int,
) -> float:
    """计算像素/点的缩放比例.

    按宽度计算（image_w / page_w_pts）。
    正常渲染下宽度与高度的 scale 应几乎相等；若出现显著偏差
    （如非均匀缩放），调用方应自行处理。

    Args:
        page_w_pts: PDF 页面宽度（点单位）
        page_h_pts: PDF 页面高度（点单位）
        image_w: 渲染图像宽度（像素）
        image_h: 渲染图像高度（像素）

    Returns:
        scale = image_w / page_w_pts
    """
    return image_w / page_w_pts if page_w_pts else 1.0


def image_to_pdf_bbox(
    bbox_img: tuple[float, float, float, float],
    page_h_pts: float,
    scale: float,
) -> tuple[float, float, float, float]:
    """图像坐标 → PDF 坐标（返回 tuple，便于 JSON 序列化）.

    Args:
        bbox_img: (x1, y1, x2, y2)，图像坐标系，左上角原点
        page_h_pts: PDF 页面高度（点单位）
        scale: 像素/点 缩放比例

    Returns:
        (x1, y1, x2, y2)，PDF 坐标系，左下角原点
    """
    x1_img, y1_img, x2_img, y2_img = bbox_img
    x1 = x1_img / scale
    x2 = x2_img / scale
    y1 = page_h_pts - y2_img / scale
    y2 = page_h_pts - y1_img / scale
    return (x1, y1, x2, y2)


def pdf_to_image_bbox(
    bbox_pdf: tuple[float, float, float, float],
    page_h_pts: float,
    scale: float,
) -> tuple[float, float, float, float]:
    """PDF 坐标 → 图像坐标（返回 tuple）.

    Args:
        bbox_pdf: (x1, y1, x2, y2)，PDF 坐标系，左下角原点
        page_h_pts: PDF 页面高度（点单位）
        scale: 像素/点 缩放比例

    Returns:
        (x1, y1, x2, y2)，图像坐标系，左上角原点
    """
    x1_pdf, y1_pdf, x2_pdf, y2_pdf = bbox_pdf
    x1 = x1_pdf * scale
    x2 = x2_pdf * scale
    y1 = (page_h_pts - y2_pdf) * scale
    y2 = (page_h_pts - y1_pdf) * scale
    return (x1, y1, x2, y2)


def img_to_pdf_rect(
    bbox_img: tuple[float, float, float, float],
    page_height_px: float,
    scale: float,
) -> fitz.Rect:
    """将图像坐标（左上角原点，像素）转换为 PDF 坐标（左下角原点，点）.

    .. deprecated::
        新代码请使用 `image_to_pdf_bbox()`，参数语义更清晰
        （使用 page_h_pts 而非 page_height_px）。

    Args:
        bbox_img: (x1, y1, x2, y2)，图像坐标系，左上角原点
        page_height_px: 整页图像高度（像素）
        scale: 像素/点 的缩放比例（scale = img_width_px / page_width_pts）

    Returns:
        fitz.Rect，PDF 坐标系（左下角原点）
    """
    x1_img, y1_img, x2_img, y2_img = bbox_img
    x1 = x1_img / scale
    x2 = x2_img / scale
    # Y 轴翻转：图像 y=0 是顶部，PDF y=0 是底部
    y1 = (page_height_px - y2_img) / scale
    y2 = (page_height_px - y1_img) / scale
    return fitz.Rect(x1, y1, x2, y2)


def pdf_to_img_rect(
    bbox_pdf: fitz.Rect,
    page_height_px: float,
    scale: float,
) -> tuple[int, int, int, int]:
    """将 PDF 坐标转换为图像坐标.

    .. deprecated::
        新代码请使用 `pdf_to_image_bbox()`，参数语义更清晰
        （使用 page_h_pts 而非 page_height_px）。

    Args:
        bbox_pdf: fitz.Rect，PDF 坐标系（左下角原点）
        page_height_px: 整页图像高度（像素）
        scale: 像素/点 的缩放比例

    Returns:
        (x1, y1, x2, y2)，图像坐标系，左上角原点
    """
    x1 = int(bbox_pdf.x0 * scale)
    x2 = int(bbox_pdf.x1 * scale)
    y1_img_bottom = int(bbox_pdf.y0 * scale)
    y2_img_top = int(bbox_pdf.y1 * scale)
    # Y 轴翻转
    y1 = int(page_height_px - y2_img_top)
    y2 = int(page_height_px - y1_img_bottom)
    return (x1, y1, x2, y2)


# ---------------------------------------------------------------------------
# 屏幕坐标 ↔ 图像坐标
# ---------------------------------------------------------------------------

def screen_to_img_rect(
    bbox_screen: QRect,
    view_scale: float,
) -> tuple[float, float, float, float]:
    """将屏幕控件坐标转换为页面图像坐标.

    PDFViewer 中每页的 QLabel 大小等于渲染后的 pixmap 大小，
    因此屏幕坐标只需除以当前视图缩放比例即可得到图像坐标。

    Args:
        bbox_screen: QRect，控件内坐标（左上角原点，像素）
        view_scale: 当前视图的缩放比例（render scale，如 1.5）

    Returns:
        (x1, y1, x2, y2)，页面图像坐标
    """
    x1 = bbox_screen.left() / view_scale
    y1 = bbox_screen.top() / view_scale
    x2 = bbox_screen.right() / view_scale
    y2 = bbox_screen.bottom() / view_scale
    return (x1, y1, x2, y2)


def img_to_screen_rect(
    bbox_img: tuple[float, float, float, float],
    view_scale: float,
) -> QRect:
    """将页面图像坐标转换为屏幕控件坐标.

    Args:
        bbox_img: (x1, y1, x2, y2)，页面图像坐标
        view_scale: 当前视图的缩放比例

    Returns:
        QRect，控件内坐标
    """
    x1, y1, x2, y2 = bbox_img
    return QRect(
        int(x1 * view_scale),
        int(y1 * view_scale),
        int((x2 - x1) * view_scale),
        int((y2 - y1) * view_scale),
    )


# ---------------------------------------------------------------------------
# 屏幕坐标 → PDF 坐标（一站式转换）
# ---------------------------------------------------------------------------

def screen_to_pdf_rect(
    bbox_screen: QRect,
    view_scale: float,
    page_height_px: float,
    pdf_scale: float,
) -> fitz.Rect:
    """屏幕控件坐标 → PDF 坐标（一站式转换）.

    Args:
        bbox_screen: 控件内屏幕坐标
        view_scale: 视图缩放比例（如 1.5）
        page_height_px: 整页渲染图像高度（像素）
        pdf_scale: 像素/点 比例（由渲染 DPI 决定）

    Returns:
        fitz.Rect，PDF 坐标
    """
    bbox_img = screen_to_img_rect(bbox_screen, view_scale)
    return img_to_pdf_rect(bbox_img, page_height_px, pdf_scale)


# ---------------------------------------------------------------------------
# 辅助：从 fitz.Page 计算渲染参数
# ---------------------------------------------------------------------------

def get_render_params(page: fitz.Page, dpi: int = 300) -> tuple[float, int, int]:
    """计算页面渲染参数.

    Args:
        page: fitz.Page 对象
        dpi: 渲染 DPI

    Returns:
        (scale, width_px, height_px)
        - scale: 像素/点 比例
        - width_px: 渲染图像宽度
        - height_px: 渲染图像高度
    """
    pix = page.get_pixmap(dpi=dpi)
    scale = pix.width / page.rect.width
    return scale, pix.width, pix.height
