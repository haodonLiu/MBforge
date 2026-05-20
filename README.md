# MBForge - Molecular Knowledge Base & AI Workbench

类似 Obsidian + Zotero 的分子科学知识库平台，支持 PDF OCR 解析、分子数据建库、LLM 智能对话，以及可扩展的分子生成/对接/QSAR/MD 工作流。

## 核心特性

- **Vault 项目管理**：一个文件夹即一个项目，类似 Obsidian
- **层级文件存储**：支持 Markdown、PDF、文本、分子数据文件
- **PDF 解析流水线**：OCR/文本提取 → 分子识别 → LLM 归纳 → 向量索引
- **知识库检索**：基于 ChromaDB 的语义搜索 + Rerank 重排序
- **LLM 对话框**：支持流式输出、知识库上下文增强
- **分子数据库**：SQLite + RDKit，支持活性数据、性质计算
- **工作流扩展接口**：预留分子生成/对接/QSAR/MD 模块
- **本地模型支持**：Embedding、Rerank、LLM、VLM 可配置本地或 API

## 安装

```bash
# 使用 uv 安装依赖
uv sync --dev

# 或安装为可编辑模式
uv pip install -e .
```

## 使用

### 命令行

```bash
# 启动 GUI
mbforge
mbforge gui

# 新建项目
mbforge init ./my-project --name "MyProject"

# 索引项目文件（后台）
mbforge index ./my-project
```

### Python 模块

```bash
python -m mbforge
```

### 打包为 EXE

```bash
uv run python build.py
# 或
pyinstaller MBForge.spec
```

## 项目结构

```
src/mbforge/
├── core/           # 核心数据模型（Project, KnowledgeBase, MoleculeDatabase）
├── models/         # AI 模型接口（LLM, Embedding, Rerank, VLM）
├── parsers/        # PDF 解析与分子提取
├── ui/             # PyQt6 图形界面
├── workflow/       # 分子工作流扩展接口
└── utils/          # 工具函数与配置
```

## 技术栈

- **UI**: PyQt6 + QWebEngineView (Markdown 预览)
- **向量数据库**: ChromaDB
- **Embedding**: sentence-transformers / OpenAI API
- **LLM**: OpenAI 兼容 API（支持 vLLM、Ollama、硅基流动等）
- **化学信息学**: RDKit
- **PDF 解析**: PyMuPDF
- **包管理**: uv
- **测试**: pytest

## 配置

首次运行后，全局配置存储在：
- Windows: `%APPDATA%/MBForge/config.json`
- macOS: `~/Library/Application Support/MBForge/config.json`
- Linux: `~/.config/MBForge/config.json`

每个项目的配置和索引存储在项目根目录的 `.mbforge/` 中。

## 开发

```bash
# 运行测试
uv run pytest tests/unit/ -v

# 代码格式化
uv run ruff format src/
```

## 许可

MIT
