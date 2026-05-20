#!/usr/bin/env bash
# MBForge 一键配置入口
# 用法: bash setup/index.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULES="$SCRIPT_DIR/modules"

# 加载公共函数
source "$SCRIPT_DIR/common.sh"

echo -e "${BOLD}"
echo "╔══════════════════════════════════════════╗"
echo "║     MBForge 一键配置（交互式）           ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# 按顺序加载并执行模块
source "$MODULES/01_check_env.sh"
source "$MODULES/02_config_uniparser.sh"
source "$MODULES/03_detect_ollama.sh"
source "$MODULES/04_config_llm.sh"
source "$MODULES/05_config_models.sh"
source "$MODULES/06_install_modelscope.sh"
source "$MODULES/07_write_env.sh"
source "$MODULES/08_verify.sh"

run_check_env
run_config_uniparser
run_detect_ollama
run_config_llm
run_config_models
run_install_modelscope
run_write_env
run_verify
