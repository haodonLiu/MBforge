"""SAR (结构-活性关系) 分析模块.

本模块提供结构-活性关系(SAR)分析功能，
用于理解分子结构变化如何影响生物活性。

主要功能:
    - 活性数据预处理: 单位转换、删失数据、pActivity、异常值检测
    - 聚类活性统计: 计算每个聚类的活性均值、标准差等
    - 贡献分析: 分析不同子结构对活性的贡献
    - 活性分布: 分析活性值的分布特征

主要类:
    ActivityPreprocessor: 活性数据预处理器
    SARAnalyzer: SAR分析器，执行完整的SAR分析
    SARResult: SAR分析结果数据类

示例:
    >>> from mbforge.sar import ActivityPreprocessor, SARAnalyzer
    >>> prep = ActivityPreprocessor()
    >>> processed = prep.preprocess(raw_activities)
    >>> analyzer = SARAnalyzer()
    >>> results = analyzer.analyze_clusters(clusters, mcs_results)
"""

# 从子模块导入主要类和异常
from .preprocessor import (
    ActivityPreprocessor,
    CensoredType,
)  # 活性预处理
from .analyzer import SARAnalyzer, SARError, SARResult  # SAR分析器

# 模块公开接口
__all__ = [
    "ActivityPreprocessor",  # 活性数据预处理器
    "CensoredType",  # 删失类型枚举
    "SARAnalyzer",  # SAR分析器
    "SARError",  # SAR分析异常
    "SARResult",  # SAR结果数据类
]
