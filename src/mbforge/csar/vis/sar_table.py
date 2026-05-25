"""SAR表格可视化模块 - 带取代基图像.

本模块提供SAR表格的可视化功能，
用于展示分子骨架与不同取代基组合对活性的影响。

功能:
    - 取代基图像渲染: 将取代基渲染为2D图像
    - SAR表格生成: 创建包含骨架和取代基的表格图像
    - 活性颜色编码: 根据活性值使用不同颜色

注意:
    - 表格图像创建逻辑已统一到 utils.py 的 create_sar_table_image()
    - 本模块保留 create_substituent_table_image() 以保持向后兼容

示例:
    >>> from mbforge.csar_vis.sar_table import create_substituent_table_image
    >>> table_img = create_substituent_table_image(rows, col_labels, activity_col)
    >>> table_img.save("sar_table.png")
"""

from __future__ import annotations

import logging
from typing import Any

from PIL import Image

from .utils import create_sar_table_image, SUBSTITUENT_SIZE

logger = logging.getLogger(__name__)


def create_substituent_table_image(
    rows: list[list[Any]],
    col_labels: list[str],
    activity_col_index: int,
    size: tuple[int, int] = SUBSTITUENT_SIZE,
) -> Image.Image:
    """创建带取代基图像的表格图像 (向后兼容包装器).

    内部委托给 utils.create_sar_table_image()，启用活性颜色编码。

    Args:
        rows: 行列表.
        col_labels: 列标签.
        activity_col_index: 活性列索引.
        size: 取代基尺寸.

    Returns:
        PIL 图像.
    """
    return create_sar_table_image(
        rows=rows,
        col_labels=col_labels,
        sub_size=size,
        activity_col_index=activity_col_index,
        use_activity_colors=True,
    )
