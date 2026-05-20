#!/usr/bin/env bash
# MBForge 一键配置脚本（交互式）
# 用法: bash setup.sh
set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }
header(){ echo -e "\n${BOLD}═══ $* ═══${NC}"; }

PYTHON=".venv/Scripts/python.exe"

# ═══════════════════════════════════════════════════════
# 1. 基础环境检查
# ═══════════════════════════════════════════════════════
header "基础环境检查"

if ! command -v uv &>/dev/null; then
    fail "未找到 uv，请先安装: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi
ok "uv $(uv --version)"

if [ ! -d ".venv" ]; then
    info "创建虚拟环境 (Python 3.12) ..."
    uv venv .venv --python 3.12
    ok "虚拟环境已创建"
else
    ok "虚拟环境已存在"
fi

info "安装依赖 ..."
uv sync --dev
ok "主依赖安装完成"

if ! $PYTHON -c "import csar" 2>/dev/null; then
    info "安装 openSAR (csar) ..."
    uv pip install -e openSAR/ --python .venv/Scripts/python.exe
    ok "csar 已安装"
else
    ok "csar 已存在"
fi

# ═══════════════════════════════════════════════════════
# 2. UniParser 配置
# ═══════════════════════════════════════════════════════
header "UniParser 配置"

UNIPARSER_HOST=""
UNIPARSER_KEY=""

read -rp "是否配置 UniParser 远程解析服务？[Y/n]: " configure_uniparser
if [[ "${configure_uniparser,,}" != "n" ]]; then
    read -rp "UniParser 服务地址 [https://your-server.com]: " UNIPARSER_HOST
    UNIPARSER_HOST="${UNIPARSER_HOST:-https://your-server.com}"
    read -rp "UniParser API Key: " UNIPARSER_KEY
    UNIPARSER_KEY="${UNIPARSER_KEY:-}"
    if [ -n "$UNIPARSER_KEY" ]; then
        ok "UniParser 已配置: $UNIPARSER_HOST"
    else
        warn "未填写 API Key，UniParser 将不可用"
    fi
else
    info "跳过 UniParser 配置"
fi

# ═══════════════════════════════════════════════════════
# 3. Ollama 检测
# ═══════════════════════════════════════════════════════
header "Ollama 本地模型检测"

OLLAMA_AVAILABLE=false
OLLAMA_HOST="http://localhost:11434"

if command -v ollama &>/dev/null; then
    OLLAMA_AVAILABLE=true
    ok "检测到 Ollama: $(ollama --version 2>&1 | head -1)"
    # 检查 ollama 是否运行
    if curl -s "$OLLAMA_HOST/api/tags" &>/dev/null; then
        ok "Ollama 服务运行中"
        MODELS=$($PYTHON -c "
import urllib.request, json
try:
    data = json.loads(urllib.request.urlopen('$OLLAMA_HOST/api/tags').read())
    for m in data.get('models', []):
        print(f\"  - {m['name']}\")
except: pass
" 2>/dev/null || true)
        if [ -n "$MODELS" ]; then
            info "已安装模型:"
            echo "$MODELS"
        fi
    else
        warn "Ollama 已安装但服务未运行，请执行: ollama serve"
    fi
else
    info "未检测到 Ollama，跳过本地模型配置"
    info "后续可安装: https://ollama.com/download"
fi

# ═══════════════════════════════════════════════════════
# 4. LLM 配置
# ═══════════════════════════════════════════════════════
header "LLM 大语言模型配置"

LLM_PROVIDER="openai_compatible"
LLM_BASE_URL="https://api.siliconflow.cn/v1"
LLM_API_KEY=""
LLM_MODEL="Qwen/Qwen2.5-7B-Instruct"

echo "选择 LLM 提供商:"
echo "  1) OpenAI 兼容 API（硅基流动 / vLLM / 其他兼容服务）"
echo "  2) Anthropic（Claude / MiniMax Anthropic 兼容）"
if $OLLAMA_AVAILABLE; then
    echo "  3) Ollama（本地模型）"
fi
read -rp "选择 [1]: " llm_choice
llm_choice="${llm_choice:-1}"

case $llm_choice in
    1)
        LLM_PROVIDER="openai_compatible"
        read -rp "API Base URL [$LLM_BASE_URL]: " input; LLM_BASE_URL="${input:-$LLM_BASE_URL}"
        read -rp "API Key: " LLM_API_KEY
        read -rp "模型名称 [$LLM_MODEL]: " input; LLM_MODEL="${input:-$LLM_MODEL}"
        ;;
    2)
        LLM_PROVIDER="anthropic"
        LLM_BASE_URL="https://api.minimaxi.com/anthropic"
        read -rp "API Base URL [$LLM_BASE_URL]: " input; LLM_BASE_URL="${input:-$LLM_BASE_URL}"
        read -rp "API Key: " LLM_API_KEY
        read -rp "模型名称 [MiniMax-M2.7]: " input; LLM_MODEL="${input:-MiniMax-M2.7}"
        ;;
    3)
        if $OLLAMA_AVAILABLE; then
            LLM_PROVIDER="ollama"
            LLM_BASE_URL="$OLLAMA_HOST/v1"
            LLM_API_KEY="ollama"
            read -rp "模型名称 [qwen2.5:7b]: " input; LLM_MODEL="${input:-qwen2.5:7b}"
        fi
        ;;
esac

ok "LLM: $LLM_PROVIDER / $LLM_MODEL"

# ═══════════════════════════════════════════════════════
# 5. Embedding & Rerank 模型配置
# ═══════════════════════════════════════════════════════
header "Embedding / Rerank 模型配置"

EMBED_PROVIDER="sentence_transformers"
EMBED_MODEL="BAAI/bge-small-zh-v1.5"
EMBED_DEVICE="cpu"
RERANK_MODEL="BAAI/bge-reranker-base"
RERANK_DEVICE="cpu"

# 检测 CUDA
HAS_CUDA=false
if $PYTHON -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
    HAS_CUDA=true
    GPU_NAME=$($PYTHON -c "import torch; print(torch.cuda.get_device_name(0))" 2>/dev/null || echo "unknown")
    ok "检测到 GPU: $GPU_NAME"
fi

echo ""
echo "Embedding 模型选择:"
echo "  1) BAAI/bge-small-zh-v1.5（轻量，推荐 CPU）"
echo "  2) BAAI/bge-large-zh-v1.5（高精度）"
echo "  3) Qwen/Qwen3-Embedding-0.6B（通义千问，推荐）"
echo "  4) 使用 API（OpenAI / 兼容接口）"
read -rp "选择 [1]: " embed_choice
embed_choice="${embed_choice:-1}"

case $embed_choice in
    1) EMBED_MODEL="BAAI/bge-small-zh-v1.5" ;;
    2) EMBED_MODEL="BAAI/bge-large-zh-v1.5" ;;
    3) EMBED_MODEL="Qwen/Qwen3-Embedding-0.6B" ;;
    4)
        EMBED_PROVIDER="api"
        read -rp "Embedding API Base URL: " EMBED_BASE_URL
        read -rp "Embedding API Key: " EMBED_API_KEY
        read -rp "模型名称 [$EMBED_MODEL]: " input; EMBED_MODEL="${input:-$EMBED_MODEL}"
        ;;
esac

if $HAS_CUDA; then
    read -rp "使用 GPU 加速？[Y/n]: " use_gpu
    if [[ "${use_gpu,,}" != "n" ]]; then
        EMBED_DEVICE="cuda"
    fi
fi

echo ""
echo "Rerank 模型选择:"
echo "  1) BAAI/bge-reranker-base（默认）"
echo "  2) BAAI/bge-reranker-v2-m3（多语言）"
echo "  3) Qwen/Qwen3-Reranker-0.6B（通义千问，推荐）"
read -rp "选择 [1]: " rerank_choice
rerank_choice="${rerank_choice:-1}"

case $rerank_choice in
    1) RERANK_MODEL="BAAI/bge-reranker-base" ;;
    2) RERANK_MODEL="BAAI/bge-reranker-v2-m3" ;;
    3) RERANK_MODEL="Qwen/Qwen3-Reranker-0.6B" ;;
esac

if $HAS_CUDA; then
    RERANK_DEVICE="$EMBED_DEVICE"
fi

ok "Embedding: $EMBED_MODEL ($EMBED_DEVICE)"
ok "Rerank: $RERANK_MODEL ($RERANK_DEVICE)"

# ═══════════════════════════════════════════════════════
# 6. ModelScope 模型下载
# ═══════════════════════════════════════════════════════
header "模型下载（可选）"

if command -v modelscope &>/dev/null || $PYTHON -c "import modelscope" 2>/dev/null; then
    ok "ModelScope 已安装"

    read -rp "是否下载推荐的 Embedding/Rerank 模型到本地？[Y/n]: " download_models
    if [[ "${download_models,,}" != "n" ]]; then
        info "下载 $EMBED_MODEL ..."
        $PYTHON -c "
from modelscope.hub.snapshot_download import snapshot_download
snapshot_download('$EMBED_MODEL')
print('Downloaded: $EMBED_MODEL')
" 2>/dev/null && ok "$EMBED_MODEL 下载完成" || warn "$EMBED_MODEL 下载失败"

        info "下载 $RERANK_MODEL ..."
        $PYTHON -c "
from modelscope.hub.snapshot_download import snapshot_download
snapshot_download('$RERANK_MODEL')
print('Downloaded: $RERANK_MODEL')
" 2>/dev/null && ok "$RERANK_MODEL 下载完成" || warn "$RERANK_MODEL 下载失败"
    fi
else
    echo "ModelScope 未安装。是否安装？"
    echo "  安装后可离线下载模型，加速首次加载"
    read -rp "安装 ModelScope？[y/N]: " install_modelscope
    if [[ "${install_modelscope,,}" == "y" ]]; then
        info "安装 ModelScope ..."
        uv pip install modelscope --python .venv/Scripts/python.exe
        ok "ModelScope 已安装"
    fi
fi

# ═══════════════════════════════════════════════════════
# 7. 写入 .env 文件
# ═══════════════════════════════════════════════════════
header "写入配置文件"

if [ -f ".env" ]; then
    read -rp ".env 已存在，是否覆盖？[y/N]: " overwrite
    if [[ "${overwrite,,}" != "y" ]]; then
        info "保留现有 .env"
    else
        cp .env .env.bak 2>/dev/null && ok "已备份旧 .env → .env.bak"
    fi
fi

# 只在覆盖或不存在时写入
if [[ "${overwrite,,}" == "y" ]] || [ ! -f ".env" ]; then
    cat > .env << ENVEOF
# UniParser Configuration
UNIPARSER_HOST=${UNIPARSER_HOST:-}
UNIPARSER_API_KEY=${UNIPARSER_KEY:-}

# ---------- LLM ----------
MBFORGE_LLM_PROVIDER=${LLM_PROVIDER}
MBFORGE_LLM_BASE_URL=${LLM_BASE_URL}
MBFORGE_LLM_API_KEY=${LLM_API_KEY}
MBFORGE_LLM_MODEL=${LLM_MODEL}
MBFORGE_LLM_MAX_TOKENS=4096
MBFORGE_LLM_TEMPERATURE=0.7
MBFORGE_LLM_TOP_P=0.9

# ---------- Embedding ----------
MBFORGE_EMBED_PROVIDER=${EMBED_PROVIDER}
MBFORGE_EMBED_MODEL=${EMBED_MODEL}
MBFORGE_EMBED_DEVICE=${EMBED_DEVICE}
MBED_BASE_URL=${EMBED_BASE_URL:-}
MBED_API_KEY=${EMBED_API_KEY:-}

# ---------- Rerank ----------
MBFORGE_RERANK_MODEL=${RERANK_MODEL}
MBFORGE_RERANK_DEVICE=${RERANK_DEVICE}

# ---------- UV Mirror ----------
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
UV_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
UV_PYTHON_MIRRORS=https://mirror.sjtu.edu.cn/python-request
ENVEOF
    ok ".env 已写入"
fi

# ═══════════════════════════════════════════════════════
# 8. 验证
# ═══════════════════════════════════════════════════════
header "验证安装"

FAIL=0

$PYTHON -c "import torch; v=torch.__version__; print(f'PyTorch {v}, CUDA={torch.cuda.is_available()}')" 2>/dev/null \
    && ok "PyTorch OK" || { warn "PyTorch 异常"; FAIL=1; }

$PYTHON -c "import lxml.etree; print(f'lxml {lxml.etree.__version__}')" 2>/dev/null \
    && ok "lxml OK" || { warn "lxml 异常"; FAIL=1; }

$PYTHON -c "import csar; print(f'csar {csar.__version__}')" 2>/dev/null \
    && ok "csar OK" || { warn "csar 异常"; FAIL=1; }

$PYTHON -c "import mbforge; print(f'mbforge {mbforge.__version__}')" 2>/dev/null \
    && ok "mbforge OK" || { warn "mbforge 异常"; FAIL=1; }

echo ""
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  配置完成! 运行 uv run mbforge 启动应用  ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
else
    echo -e "${YELLOW}╔══════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║  配置完成，部分组件有警告请检查上方      ║${NC}"
    echo -e "${YELLOW}╚══════════════════════════════════════════╝${NC}"
fi
