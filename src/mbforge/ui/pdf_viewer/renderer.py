"""PDF 渲染工具与全局线程池."""

from __future__ import annotations

import atexit
import os
from concurrent.futures import ThreadPoolExecutor

import fitz  # PyMuPDF
from PyQt6.QtGui import QImage

# 全局线程池，最多 4 个 worker（防止大文档渲染时过度抢占 CPU）
_NWORKERS = min(4, max(1, os.cpu_count() or 4))
_executor: ThreadPoolExecutor = ThreadPoolExecutor(
    max_workers=_NWORKERS, thread_name_prefix="pdf_render"
)
atexit.register(lambda: _executor.shutdown(wait=True))


def _render_page_batch(
    path: str, scale: float, page_items: list[tuple[int, int]]
) -> list[tuple[int, QImage]]:
    """从 PDF 文件批量渲染页面.

    Args:
        path: PDF 文件路径（原始PDF或分片PDF）
        scale: 缩放比例
        page_items: [(doc_index, global_index), ...]，doc_index 为文件内页码

    Returns:
        [(global_index, QImage), ...]
    """
    results = []
    doc = fitz.open(path)
    try:
        for doc_idx, global_idx in page_items:
            page = doc[doc_idx]
            mat = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=mat)
            img = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            )
            results.append((global_idx, img))
    finally:
        doc.close()
    return results


def page_to_pixmap(page, scale: float) -> QImage:
    """将 fitz.Page 转为 QImage."""
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat)
    return QImage(
        pix.samples,
        pix.width,
        pix.height,
        pix.stride,
        QImage.Format.Format_RGB888,
    )
