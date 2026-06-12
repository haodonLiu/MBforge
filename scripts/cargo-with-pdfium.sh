#!/usr/bin/env bash
# cargo-with-pdfium.sh — 可选覆盖：将 PDFIUM 指向非默认位置后调用 cargo
# 用法: ./scripts/cargo-with-pdfium.sh build
#   或: ./scripts/cargo-with-pdfium.sh check --all-targets
#
# 默认安装路径 $HOME/.cache/mbforge/pdfium/ 已被 src-tauri/vendor/liteparse-pdfium-sys
# 的 build.rs 硬编码支持，裸 `cargo build` 即可工作。
# 此 wrapper 仅在需要指向其他安装位置（如 PDFIUM_INSTALL_DIR 自定义）时使用。

set -euo pipefail

# 切到 src-tauri（Cargo.toml 所在）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../src-tauri"

USER_HOME="${HOME:-${USERPROFILE:-$(eval echo ~$USER)}}"
INSTALL_DIR="${PDFIUM_INSTALL_DIR:-$USER_HOME/.cache/mbforge/pdfium}"

export PDFIUM_LIB_PATH="$INSTALL_DIR/lib"
export PDFIUM_INCLUDE_PATH="$INSTALL_DIR/include"

if [[ ! -d "$PDFIUM_LIB_PATH" ]]; then
    echo "ERROR: PDFium not installed at $INSTALL_DIR" >&2
    echo "Run: pwsh -File vendor/pdfium/setup.ps1" >&2
    exit 1
fi

echo "PDFIUM_LIB_PATH     = $PDFIUM_LIB_PATH"
echo "PDFIUM_INCLUDE_PATH = $PDFIUM_INCLUDE_PATH"

exec cargo "$@"
