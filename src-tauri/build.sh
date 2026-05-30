#!/bin/bash
# MBForge 构建脚本 — 自动设置 PDFium 路径
#
# 用法: ./build.sh [cargo args...]
# 示例: ./build.sh check
#       ./build.sh test --lib

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENDOR_LIB="$SCRIPT_DIR/vendor/pdfium/release/lib"
VENDOR_INCLUDE="$SCRIPT_DIR/vendor/pdfium/release/include"

if [ -d "$VENDOR_LIB" ] && [ -d "$VENDOR_INCLUDE" ]; then
    export PDFIUM_LIB_PATH="$VENDOR_LIB"
    export PDFIUM_INCLUDE_PATH="$VENDOR_INCLUDE"
    echo "PDFium: using vendor at $VENDOR_LIB"
else
    echo "WARNING: vendor/pdfium/release not found. Run vendor/pdfium/setup.ps1 first."
fi

cargo "$@"
