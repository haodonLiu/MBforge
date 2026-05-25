"""CADD 插件模板 —— 分子对接 / 分子动力学 / FEP / QSAR 工作流.

这是一个参考实现，展示如何为 MBForge 编写 CADD 插件。
实际使用时，请复制此目录并修改:
    - meta 信息
    - 各 CADD 方法的具体实现
    - 外部程序调用方式

使用方式:
    from mbforge.plugins import PluginRegistry
    registry = PluginRegistry()
    registry.discover()

    plugin = registry.get("cadd_template")
    result = plugin.run_docking(ligand_mol, receptor_pdb="protein.pdb")
"""

from .plugin import CADDTemplatePlugin

__all__ = ["CADDTemplatePlugin"]
