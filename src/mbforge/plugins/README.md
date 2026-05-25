# MBForge 插件系统

## 快速开始

### 1. 内置插件发现

```python
from mbforge.plugins import PluginRegistry

registry = PluginRegistry()
registry.discover(project_root=Path("./my-project"))

# 列出所有插件
print(registry.list_all())

# 获取插件实例
plugin = registry.get("cadd_template")
```

### 2. 四种插件能力

| 能力 | 说明 | 实现方法 |
|------|------|----------|
| `AGENT_TOOL` | 向 ReAct Agent 注册工具 | `register_tools(registry)` |
| `UI_PANEL` | 添加 Qt 面板 | `create_ui_panel(parent)` |
| `WORKFLOW` | 批处理工作流步骤 | `get_workflow_steps()` |
| `CLI_COMMAND` | CLI 子命令 | `register_cli(subparsers)` |

### 3. 编写自己的插件

复制 `cadd_template` 目录，修改以下内容:

**`__init__.py`**:
```python
from .plugin import MyPlugin
__all__ = ["MyPlugin"]
```

**`plugin.py`** (最小示例):
```python
from mbforge.plugins import BasePlugin, PluginMetadata, PluginCapability

class MyPlugin(BasePlugin):
    meta = PluginMetadata(
        name="my_plugin",
        version="0.1.0",
        description="我的插件",
        capabilities=[PluginCapability.AGENT_TOOL],
    )

    def register_tools(self, registry):
        registry.register(
            name="my_tool",
            description="工具描述",
            parameters_schema={"input": {"type": "string"}},
            func=lambda input: f"结果: {input}",
        )
```

### 4. 外部插件 (entry_points)

在 `pyproject.toml` 中注册:

```toml
[project.entry-points."mbforge.plugins"]
my_external_plugin = "my_package.plugin:MyPlugin"
```

## CADD 插件模板 (`cadd_template`)

提供以下工作流:

- **分子对接**: Vina, GNINA 接口 + fallback
- **分子动力学**: GROMACS, AMBER 接口框架
- **FEP**: SOMD/PMX 接口框架
- **QSAR/ADMET**: RDKit descriptors, Lipinski 规则

### 对接示例

```python
from rdkit import Chem
from rdkit.Chem import AllChem

mol = Chem.MolFromSmiles("c1ccccc1O")
mol = Chem.AddHs(mol)
AllChem.EmbedMolecule(mol)

plugin = registry.get("cadd_template")
results = plugin.run_docking(
    ligand=mol,
    receptor_pdb="protein.pdb",
    center=(10.0, 20.0, 30.0),
    engine="vina",
)
print(f"亲和力: {results[0].affinity} kcal/mol")
```

### ADMET 筛选示例

```python
result = plugin.predict_qsar(mol, model="lipinski")
print(f"Lipinski 违规: {result.descriptors['violations']}")
```

## 架构图

```
mbforge/
├── plugins/
│   ├── __init__.py          # 导出 BasePlugin, PluginRegistry
│   ├── base.py              # 插件基类与接口
│   ├── registry.py          # 发现与加载
│   ├── README.md            # 本文档
│   └── cadd_template/       # CADD 参考实现
│       ├── __init__.py
│       └── plugin.py
```
