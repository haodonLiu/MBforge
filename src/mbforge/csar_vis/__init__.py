"""SAR分析可视化模块.

本模块提供SAR分析结果的可视化功能，
包括分子结构图、活性分布图、相似度热图和SAR表格等。

可视化类型:
    - MCS结构图: 显示最大公共子结构
    - 活性分布图: 显示聚类内的活性分布
    - SAR汇总图: 显示各聚类的平均活性和大小关系
    - 相似度矩阵: 显示分子间的相似度热图
    - SAR表格: 显示骨架和取代基的对应关系

主要类:
    SARRenderer: SAR渲染器，生成各种可视化
    PlotSettings: 绘图设置

示例:
    >>> from mbforge.visualization import SARRenderer, PlotSettings
    >>> settings = PlotSettings(dpi=300, figure_size=(12, 8))
    >>> renderer = SARRenderer(settings)
    >>> renderer.render_sar_summary(results, "summary.png")
"""

# 从子模块导入主要类和异常
from .renderer import SARRenderer, RenderError  # SAR渲染器和渲染异常

# 模块公开接口
__all__ = [
    "SARRenderer",  # SAR渲染器
    "RenderError",  # 渲染异常
]
