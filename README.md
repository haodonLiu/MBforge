# MBForge - Molecular Knowledge Base & AI Workbench

> 类似 Obsidian + Zotero 的分子科学知识库平台，支持 PDF OCR 解析、分子数据建库、LLM 智能对话，以及可扩展的分子生成/对接/QSAR/MD 工作流。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/PyQt6-6.6+-green.svg)](https://doc.qt.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

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
# 使用 uv 安装依赖（推荐）
uv sync --dev

# 或安装为可编辑模式
uv pip install -e .

# 首次运行前，复制环境变量模板
cp .env.template .env
# 编辑 .env，配置 UNIPARSER_HOST、UNIPARSER_API_KEY 等
```

### 一键配置（交互式）

Linux/macOS/Git Bash:
```bash
bash setup/index.sh
```

Windows CMD:
```cmd
setup\index.bat
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
MBForge/
├── src/mbforge/          # 主应用源码
│   ├── core/             # 核心数据模型
│   │   ├── project.py         # Vault 项目管理
│   │   ├── knowledge_base.py   # ChromaDB 向量知识库
│   │   ├── mol_database.py     # SQLite 分子数据库
│   │   ├── document.py        # 文档处理
│   │   ├── summarizer.py      # LLM 摘要生成
│   │   ├── settings.py        # 项目配置
│   │   ├── memory.py         # Agent 记忆模板
│   │   └── todo_manager.py   # Todo 列表管理
│   ├── models/           # AI 模型接口
│   │   ├── base.py            # 基类定义
│   │   ├── llm.py             # OpenAI 兼容 LLM
│   │   ├── anthropic_llm.py   # Anthropic LLM
│   │   ├── embedding.py        # Embedding 模型
│   │   ├── rerank.py          # Rerank 模型
│   │   └── vlm.py             # 视觉语言模型
│   ├── parsers/          # PDF 解析与分子提取
│   │   ├── pdf_parser.py      # 解析流水线
│   │   ├── molecule_extractor.py  # 分子提取
│   │   └── file_processor.py  # 文件处理
│   ├── ui/               # PyQt6 图形界面
│   │   ├── main_window.py     # 主窗口
│   │   ├── chat_widget.py     # 对话组件
│   │   ├── pdf_viewer.py      # PDF 查看器
│   │   ├── mol_panel.py       # 分子面板
│   │   ├── mol_renderer.py    # 分子渲染
│   │   ├── file_tree.py      # 项目文件树
│   │   ├── editor.py         # Markdown 编辑器
│   │   ├── preview.py        # Markdown 预览
│   │   └── dialogs.py        # 设置对话框
│   ├── agent/            # AI Agent
│   │   ├── agent.py           # Agent 协调器
│   │   ├── context.py         # 分层上下文
│   │   ├── executor.py         # 工具执行器
│   │   ├── memory_manager.py  # 记忆管理
│   │   ├── trajectory.py      # 轨迹跟踪
│   │   └── archive_agent.py  # 归档搜索 Agent
│   ├── workflow/         # 工作流扩展
│   │   ├── base.py           # 基类
│   │   ├── generation.py      # 分子生成（占位）
│   │   ├── docking.py        # 分子对接（占位）
│   │   ├── qsar.py           # QSAR（占位）
│   │   └── md.py             # 分子动力学（占位）
│   ├── parser_io/        # UniParser 集成
│   │   ├── client.py          # UniParser 客户端
│   │   ├── config.py          # 解析器配置
│   │   └── models.py          # 数据模型
│   ├── utils/            # 工具函数
│   │   ├── config.py          # 配置管理
│   │   ├── constants.py       # 常量定义
│   │   ├── helpers.py         # 辅助函数
│   │   ├── logger.py          # 日志
│   │   └── error_logger.py    # 错误日志
│   ├── cli.py             # CLI 入口
│   └── app.py             # GUI 应用入口
├── setup/                # 一键配置脚本
│   ├── openSAR/           # SAR 分析工具箱（uv workspace member）
│   └── UniParser-Tools/  # PDF 解析 API（uv workspace member）
├── tests/                # 测试
├── docs/                 # 项目文档
│   ├── ARCHITECTURE.md        # 系统架构
│   ├── API.md                # API 参考
│   ├── TECH_STACK.md         # 技术栈
│   └── DEVELOPMENT.md        # 开发指南
└── REFERENCES.md          # 引用文献
```

## 技术栈

| 类别 | 技术 | 版本 |
|------|------|------|
| **UI** | PyQt6 + QWebEngineView | >= 6.6 |
| **向量数据库** | ChromaDB | >= 0.4 |
| **Embedding** | sentence-transformers / OpenAI API | >= 2.5 |
| **LLM** | OpenAI 兼容 API（支持 vLLM、Ollama、硅基流动等） | - |
| **化学信息学** | RDKit | >= 2024.3 |
| **PDF 解析** | PyMuPDF | >= 1.25 |
| **深度学习** | PyTorch (CUDA 12.8) | >= 2.6 |
| **包管理** | uv | - |
| **测试** | pytest | >= 7.0 |

详见 [docs/TECH_STACK.md](docs/TECH_STACK.md)。

## 配置

首次运行后，全局配置存储在：
- Windows: `%APPDATA%/MBForge/config.json`
- macOS: `~/Library/Application Support/MBForge/config.json`
- Linux: `~/.config/MBForge/config.json`

每个项目的配置和索引存储在项目根目录的 `.mbforge/` 中。

详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 中的配置系统章节。

## 开发

```bash
# 运行测试
uv run pytest tests/unit/ -v

# 代码格式化
uv run ruff format src/

# Lint 检查
uv run ruff check src/

# 类型检查
uv run mypy src/
```

详见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

## 文档

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - 系统架构设计
- [API.md](docs/API.md) - 公共 API 参考
- [TECH_STACK.md](docs/TECH_STACK.md) - 技术栈详解
- [DEVELOPMENT.md](docs/DEVELOPMENT.md) - 开发指南
- [REFERENCES.md](REFERENCES.md) - 引用文献

## 许可

MIT License
