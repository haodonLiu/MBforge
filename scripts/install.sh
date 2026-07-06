#!/usr/bin/env bash
# MBForge 一键安装脚本
# 跨平台：Linux / macOS / Windows (Git Bash / WSL)
# 需求：Python 3.12.x，Node >=20.19，npm，uv（自动安装）

set -euo pipefail

# 颜色输出
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { printf "${GREEN}[✓]${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}[!]${NC} %s\n" "$*"; }
fail() { printf "${RED}[✗]${NC} %s\n" "$*" >&2; exit 1; }

# 路径
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=========================================="
echo "  MBForge 一键安装"
echo "  $(uname -s) | $(uname -m)"
echo "=========================================="

# ---- 1. Python 检查 ----
if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
    fail "Python 未安装。需要 Python 3.12.x。"
fi
PY=$(command -v python3 || command -v python)
PY_VERSION=$($PY -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
PY_MAJOR=$($PY -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$($PY -c 'import sys; print(sys.version_info.minor)')

if [ "$PY_MAJOR" -ne 3 ] || [ "$PY_MINOR" -ne 12 ]; then
    fail "Python 版本不符：${PY_VERSION}（要求 3.12.x）。pyproject.toml 锁定 >=3.12,<3.13。"
fi
info "Python ${PY_VERSION}"

# ---- 2. Node 检查 ----
if ! command -v node >/dev/null 2>&1; then
    fail "Node 未安装。需要 Node >=20.19（Vite 8 baseline）。"
fi
NODE_VERSION=$(node --version | sed 's/v//')
NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1)
NODE_MINOR=$(echo "$NODE_VERSION" | cut -d. -f2)
if [ "$NODE_MAJOR" -lt 20 ] || { [ "$NODE_MAJOR" -eq 20 ] && [ "$NODE_MINOR" -lt 19 ]; }; then
    fail "Node 版本过低：${NODE_VERSION}（要求 >=20.19）。"
fi
info "Node ${NODE_VERSION}"

if ! command -v npm >/dev/null 2>&1; then
    fail "npm 未安装。"
fi
NPM_VERSION=$(npm --version)
info "npm ${NPM_VERSION}"

# ---- 3. uv 安装 ----
if ! command -v uv >/dev/null 2>&1; then
    warn "uv 未安装，正在安装…"
    if [ "$(uname -s)" = "Linux" ] || [ "$(uname -s)" = "Darwin" ]; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    else
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    fi
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uv >/dev/null 2>&1; then
        fail "uv 安装失败。请手动安装：https://docs.astral.sh/uv/"
    fi
fi
UV_VERSION=$(uv --version | awk '{print $2}')
info "uv ${UV_VERSION}"

# ---- 4. Python 依赖 ----
echo ""
echo "[1/2] 安装 Python 依赖（uv sync --dev）…"
echo "      PyTorch CUDA 12.8 + RDKit + OpenKB + MolScribe 等"
echo "      首次安装预计 5-15 分钟（取决于网速）"
echo ""
uv sync --dev --index-strategy unsafe-best-match

# ---- 5. 前端依赖 ----
echo ""
echo "[2/2] 安装前端依赖（npm install）…"
echo ""
cd "$ROOT/frontend"
npm install
cd "$ROOT"

# ---- 完成 ----
echo ""
echo "=========================================="
info "安装完成"
echo "=========================================="
echo ""
echo "下一步："
echo ""
echo "  # 启动后端 + 前端（推荐）"
echo "  python start.py"
echo ""
echo "  # 或分别启动"
echo "  uv run uvicorn mbforge.app:app --host 127.0.0.1 --port 18792"
echo "  cd frontend && npm run dev"
echo ""
echo "  # 桌面 GUI"
echo "  uv run python -m mbforge --gui"
echo ""
echo "  # 验证"
echo "  uv run pytest tests/ -v"
echo ""