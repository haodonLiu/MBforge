"""UniDock 插件 —— GPU 加速的高性能分子对接引擎.

Uni-Dock 是深势科技开发的高性能 GPU 加速分子对接引擎 (Apache 2.0 开源)，
GitHub: https://github.com/dptech-corp/Uni-Dock

支持的打分函数:
    - vina:   AutoDock Vina 打分函数
    - vinardo: Vinardo 打分函数
    - ad4:    AutoDock4 打分函数

特性:
    - GPU 加速 (V100 比单核 CPU 快 2000 倍)
    - 支持批量对接 (--batch, --gpu_batch)
    - 支持柔性侧链 (--flex)
    - 三种搜索模式: fast / balance / detail

安装方式:
    conda create -n unidock_env unidock -c conda-forge

使用方式:
    from mbforge.plugins import PluginRegistry
    registry = PluginRegistry()
    registry.discover()

    plugin = registry.get("unidock")
    result = plugin.run_docking(ligand_mol, receptor_pdb="protein.pdb")
"""

from .plugin import UniDockPlugin

__all__ = ["UniDockPlugin"]
