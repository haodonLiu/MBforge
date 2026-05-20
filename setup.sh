#!/usr/bin/env bash
# MBForge 一键配置脚本
# 用法: bash setup.sh
set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

# ---------- 1. 检查 uv ----------
info "检查 uv ..."
if ! command -v uv &>/dev/null; then
    fail "未找到 uv，请先安装: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi
ok "uv $(uv --version)"

# ---------- 2. 创建虚拟环境 ----------
if [ ! -d ".venv" ]; then
    info "创建虚拟环境 (Python 3.12) ..."
    uv venv .venv --python 3.12
    ok "虚拟环境已创建"
else
    ok "虚拟环境已存在"
fi

# ---------- 3. 安装依赖 ----------
info "安装依赖 (uv sync) ..."
uv sync --dev
ok "主依赖安装完成"

# ---------- 4. 补装 openSAR (csar) ----------
# uv workspace 在 Windows 上可能无法正确解析 openSAR，手动安装
if ! .venv/Scripts/python.exe -c "import csar" 2>/dev/null; then
    info "安装 openSAR (csar) ..."
    uv pip install -e openSAR/ --python .venv/Scripts/python.exe
    ok "csar 已安装"
else
    ok "csar 已安装"
fi

# ---------- 5. 配置 .env ----------
if [ ! -f ".env" ]; then
    info "从模板创建 .env ..."
    cp .env.template .env
    ok ".env 已创建，请编辑填入你的 API Key"
else
    ok ".env 已存在"
fi

# ---------- 6. 验证 ----------
info "验证安装 ..."

FAIL=0

.venv/Scripts/python.exe -c "import torch; assert torch.cuda.is_available(), 'CUDA not available'" 2>/dev/null \
    && ok "PyTorch CUDA $(.venv/Scripts/python.exe -c 'import torch; print(torch.__version__)')" \
    || { warn "PyTorch CUDA 不可用"; FAIL=1; }

.venv/Scripts/python.exe -c "import lxml.etree; print(f'lxml {lxml.etree.__version__}')" 2>/dev/null \
    && ok "lxml $(.venv/Scripts/python.exe -c 'import lxml.etree; print(lxml.etree.__version__)')" \
    || { warn "lxml 未安装"; FAIL=1; }

.venv/Scripts/python.exe -c "import csar; print(f'csar {csar.__version__}')" 2>/dev/null \
    && ok "csar $(.venv/Scripts/python.exe -c 'import csar; print(csar.__version__)')" \
    || { warn "csar 未安装"; FAIL=1; }

.venv/Scripts/python.exe -c "import mbforge; print(f'mbforge {mbforge.__version__}')" 2>/dev/null \
    && ok "mbforge $(.venv/Scripts/python.exe -c 'import mbforge; print(mbforge.__version__)')" \
    || { warn "mbforge 未安装"; FAIL=1; }

echo ""
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  配置完成! 运行 mbforge 启动应用${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    echo -e "${YELLOW}========================================${NC}"
    echo -e "${YELLOW}  配置完成，但有警告请检查上方输出${NC}"
    echo -e "${YELLOW}========================================${NC}"
fi
