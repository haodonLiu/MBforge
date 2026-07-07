#!/usr/bin/env bash
# MBForge Docker 镜像构建脚本
# 跨平台：Linux / macOS / Windows (Git Bash / WSL)
# 需求：Docker 20.10+，可选 nvidia-container-toolkit (GPU)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TAG="${TAG:-mbforge:dev}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { printf "${GREEN}[✓]${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}[!]${NC} %s\n" "$*"; }
fail() { printf "${RED}[✗]${NC} %s\n" "$*" >&2; exit 1; }

echo "=========================================="
echo "  MBForge Docker 构建"
echo "  TAG: ${TAG}"
echo "=========================================="

# ---- 1. Docker 检查 ----
command -v docker >/dev/null 2>&1 || fail "Docker 未安装。https://www.docker.com/products/docker-desktop/"
DOCKER_VERSION=$(docker --version | awk '{print $3}' | tr -d ',')
info "Docker ${DOCKER_VERSION}"

# ---- 2. 构建镜像 ----
echo ""
echo "[1/2] 构建镜像（首次 10-20 分钟）…"
echo ""
docker build \
    --build-arg PYTHON_VERSION=3.12 \
    --build-arg CUDA_VERSION=12.8.0 \
    -t "${TAG}" \
    -f Dockerfile \
    .

# ---- 3. GPU 检测 ----
GPU_FLAG=""
if command -v nvidia-smi >/dev/null 2>&1; then
    if docker info 2>/dev/null | grep -q "nvidia"; then
        GPU_FLAG="--gpus all"
        info "检测到 NVIDIA GPU + nvidia-container-toolkit"
    else
        warn "nvidia-smi 在，但 Docker 看不到 NVIDIA runtime（需装 nvidia-container-toolkit）"
    fi
else
    warn "未检测到 NVIDIA GPU，将以 CPU 模式运行（PyTorch CUDA 仍加载但不可用）"
fi

# ---- 4. 镜像大小 ----
echo ""
SIZE=$(docker images "${TAG}" --format "{{.Size}}" | head -1)
info "镜像大小: ${SIZE}"

# ---- 5. 完成 ----
echo ""
echo "=========================================="
info "构建完成"
echo "=========================================="
echo ""
echo "运行："
echo ""
echo "  # GPU 模式"
echo "  docker run --rm ${GPU_FLAG} -p 18792:18792 ${TAG}"
echo ""
echo "  # 数据持久化"
echo "  docker run --rm ${GPU_FLAG} -p 18792:18792 \\"
echo "    -v mbforge-config:/root/.config/MBForge \\"
echo "    -v mbforge-cache:/root/.cache \\"
echo "    ${TAG}"
echo ""
echo "访问：http://localhost:18792"
echo ""