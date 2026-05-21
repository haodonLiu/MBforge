"""MBForge - Molecular Knowledge Base & AI Workbench.

类似 Obsidian + Zotero 的知识库平台，面向药物化学与分子科学。
支持 PDF OCR 解析、分子数据建库、LLM 智能对话、以及分子生成/对接/QSAR/MD 工作流扩展。
"""

from .utils.constants import APP_VERSION

__version__ = APP_VERSION
__all__ = ["__version__"]
