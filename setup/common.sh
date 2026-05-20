#!/usr/bin/env bash
# 公共函数 — 颜色、提示、工具

# 颜色
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# Python 路径
PYTHON=".venv/Scripts/python.exe"

# 提示函数
info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }
header(){ echo -e "\n${BOLD}═══ $* ═══${NC}"; }

# 读取输入（带默认值）
ask() {
    local prompt="$1" default="$2"
    local result
    read -rp "$prompt [$default]: " result
    echo "${result:-$default}"
}

# 读取确认（y/n）
confirm() {
    local prompt="$1" default="${2:-y}"
    local result
    read -rp "$prompt[$default/Y/n]: " result
    result="${result:-$default}"
    [[ "${result,,}" != "n" ]]
}

# 检测 CUDA
detect_cuda() {
    $PYTHON -c "import torch; assert torch.cuda.is_available()" 2>/dev/null
}

# 获取 GPU 名称
get_gpu_name() {
    $PYTHON -c "import torch; print(torch.cuda.get_device_name(0))" 2>/dev/null || echo "unknown"
}

# 检测命令是否存在
has_cmd() { command -v "$1" &>/dev/null; }

# 检测 Python 模块
has_module() { $PYTHON -c "import $1" 2>/dev/null; }
