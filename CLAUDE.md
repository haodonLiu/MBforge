# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

MBForge 是一个整合 UniParser-Tools 和 openSAR 的自动化 SAR 分析流水线项目。

```
PDF → UniParser → Agent整理 → openSAR SAR分析 → 报告
```

### 模块结构

| 模块 | 用途 | 目录 |
|------|------|------|
| **parser_io** | PDF 解析 IO、配置管理、数据模型 | `src/parser_io/` |
| **openSAR** | SAR 分析工具箱（聚类、MCS、可视化） | `openSAR/` |
| **UniParser-Tools** | 文档解析 SDK | `UniParser-Tools/` |

### 统一环境配置

项目使用 `.venv` 虚拟环境，由 `uv` 管理：

```bash
# 创建虚拟环境
uv venv .venv --python 3.12

# 安装所有依赖（清华镜像）
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
uv pip install -e openSAR/ -e UniParser-Tools/ --python .venv/Scripts/python.exe

# 设置 PYTHONPATH（用于 src/ 下的模块）
export PYTHONPATH=src
```

## 快速参考

### parser_io 模块

```python
from parser_io import ParserClient, load_config

# 从 .env 加载配置
config = load_config()

# 解析 PDF
client = ParserClient(config)
result = client.parse_pdf("document.pdf")
print(f"Token: {result.token}")

# 获取结果
raw = client.get_result(result.token)
```

### openSAR

```bash
cd openSAR
pip install -e ".[dev]"
pytest tests/
csar input.xlsx -o output/
```

### UniParser-Tools

```bash
cd UniParser-Tools
uv pip install -e .
```

## 项目架构

### parser_io 模块

```
src/parser_io/
  __init__.py    # 导出 ParserClient, ParseResult, MoleculeData, SARTask
  config.py      # ParserConfig, load_config(), validate_config()
  models.py      # ParseResult, MoleculeData, SARTask
  client.py      # ParserClient（封装 UniParserClient）
```

### openSAR Pipeline

`MoleculeReader` → `MolecularClusterer`/`ScaffoldClusterer` → `MCSFinder` → `SARAnalyzer` → `SARRenderer`

Key modules:
- `src/io/` — SDF/Excel/CSV reading
- `src/clustering/` — Morgan/MACCS/RDKit fingerprints
- `src/mcs/` — Maximum Common Substructure finder
- `src/sar/` — Activity preprocessor, SAR analyzer
- `src/visualization/` — SAR summaries, similarity heatmaps

### UniParser-Tools

Token-based workflow: `trigger_*` (submit) → `get_result`/`get_formatted` (fetch)

Key modules:
- `uniparser_tools/api/clients.py` — UniParserClient HTTP wrapper
- `uniparser_tools/common/constant.py` — ParseMode/FormatFlag enums
- `uniparser_tools/common/dataclass.py` — Result dataclasses

## 环境变量

```bash
# .env 文件模板
cp .env.template .env
# 编辑配置
UNIPARSER_HOST=https://your-server.com
UNIPARSER_API_KEY=your-key
```

## Shared Patterns

- 使用 `uv` 管理虚拟环境和包安装
- 使用 `ruff` 进行 lint/format（88 字符行长）
- 使用 `pytest` 进行测试
- openSAR 使用 `mypy` 进行严格类型检查
