#!/usr/bin/env bash
# 模块 01: 检查环境 + 创建 venv + 安装依赖

run_check_env() {
    header "基础环境检查"

    # uv
    if ! has_cmd uv; then
        fail "未找到 uv，请先安装: curl -LsSf https://astral.sh/uv/install.sh | sh"
    fi
    ok "uv $(uv --version)"

    # venv
    if [ ! -d ".venv" ]; then
        info "创建虚拟环境 (Python 3.12) ..."
        uv venv .venv --python 3.12
        ok "虚拟环境已创建"
    else
        ok "虚拟环境已存在"
    fi

    # 依赖
    info "安装依赖 ..."
    uv sync --dev
    ok "主依赖安装完成"

    # csar
    if ! has_module csar; then
        info "安装 openSAR (csar) ..."
        uv pip install -e setup/openSAR/ --python "$PYTHON"
        ok "csar 已安装"
    else
        ok "csar 已存在"
    fi
}
