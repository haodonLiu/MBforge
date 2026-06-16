# MBForge 配置系统

交互式一键配置脚本，模块化设计，按需导入。

## 目录结构

```
setup/
├── README.md              ← 本文档（架构说明）
├── common.sh              ← 公共函数（颜色、提示、工具）
├── index.sh               ← Bash 入口（Linux/macOS/Git Bash）
├── index.bat              ← Windows CMD 入口
│
├── modules/               ← 配置模块（按需加载）
│   ├── 01_check_env.sh    ← 检查 uv + 创建 venv + 安装依赖
│   ├── 02_config_uniparser.sh  ← UniParser 交互配置
│   ├── 03_detect_ollama.sh     ← Ollama 自动检测
│   ├── 04_config_llm.sh        ← LLM 提供商选择与配置
│   ├── 05_config_models.sh     ← Embedding / Rerank 模型选择
│   ├── 06_install_modelscope.sh ← ModelScope 安装与模型下载
│   ├── 07_write_env.sh         ← 写入 .env 配置文件
│   └── 08_verify.sh            ← 验证安装
```

## 流程图

```
┌─────────────────────────────────────────────────────────────┐
│                     setup/index.sh                          │
│                     (入口脚本)                               │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────┐
        │ 01_check_env.sh          │
        │ 检查 uv → venv → 安装依赖 │
        └────────────┬─────────────┘
                     │
                     ▼
        ┌──────────────────────────┐
        │ 02_config_uniparser.sh   │
        │ 交互: Host + API Key     │
        └────────────┬─────────────┘
                     │
                     ▼
        ┌──────────────────────────┐
        │ 03_detect_ollama.sh      │
        │ 自动检测 ollama 安装状态  │
        └────────────┬─────────────┘
                     │
                     ▼
        ┌──────────────────────────┐
        │ 04_config_llm.sh         │
        │ 选择: OpenAI/Anthropic/   │
        │       Ollama → 填写参数   │
        └────────────┬─────────────┘
                     │
                     ▼
        ┌──────────────────────────┐
        │ 05_config_models.sh      │
        │ Embedding 模型选择       │
        │ Rerank 模型选择          │
        └────────────┬─────────────┘
                     │
                     ▼
        ┌──────────────────────────┐
        │ 06_install_modelscope.sh │
        │ 检测/安装 ModelScope     │
        │ 下载推荐模型             │
        └────────────┬─────────────┘
                     │
                     ▼
        ┌──────────────────────────┐
        │ 07_write_env.sh          │
        │ 汇总配置 → 写入 .env     │
        └────────────┬─────────────┘
                     │
                     ▼
        ┌──────────────────────────┐
        │ 08_verify.sh             │
        │ 验证 PyTorch/lxml/csar/  │
        │ mbforge 是否正常          │
        └──────────────────────────┘
```

## 模块间数据传递

各模块通过 shell 变量传递配置，公共变量定义在 `common.sh`：

| 变量 | 模块 | 说明 |
|------|------|------|
| `UNIPARSER_HOST` | 02 | UniParser 服务地址 |
| `UNIPARSER_KEY` | 02 | UniParser API Key |
| `OLLAMA_AVAILABLE` | 03 | 是否检测到 ollama |
| `LLM_PROVIDER` | 04 | LLM 提供商 |
| `LLM_BASE_URL` | 04 | LLM API 地址 |
| `LLM_API_KEY` | 04 | LLM API Key |
| `LLM_MODEL` | 04 | LLM 模型名 |
| `EMBED_PROVIDER` | 05 | Embedding 提供商 |
| `EMBED_MODEL` | 05 | Embedding 模型名 |
| `EMBED_DEVICE` | 05 | cpu/cuda |
| `RERANK_MODEL` | 05 | Rerank 模型名 |
| `RERANK_DEVICE` | 05 | cpu/cuda |

## 可选功能与已知限制

脚本验证阶段（`08_verify`）会提示以下可选功能的就绪状态：

| 功能 | 依赖 | 状态检查方式 | 不满足时的影响 |
|------|------|-------------|---------------|
| **MolDet 分子检测** | NVIDIA GPU + CUDA 12.8 | 检测 `torch.cuda.is_available()` | 前端分子检测功能不可用，其余功能正常 |

这些功能不是核心依赖，缺失时不影响 MBForge 主体功能（PDF 解析、Agent 对话、分子数据库等）。

## 添加新模块

1. 在 `modules/` 创建 `0N_xxx.sh`
2. 定义 `run_xxx()` 函数
3. 在 `index.sh` 中 `source` 并调用
4. 更新本文件的流程图
