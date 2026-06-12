# cargo-with-pdfium.ps1 — 可选覆盖：将 PDFIUM 指向非默认位置后调用 cargo
# 用法: pwsh -File scripts/cargo-with-pdfium.ps1 build
#   或: pwsh -File scripts/cargo-with-pdfium.ps1 check --all-targets
#
# 默认安装路径 $HOME/.cache/mbforge/pdfium/ 已被 src-tauri/vendor/liteparse-pdfium-sys
# 的 build.rs 硬编码支持，裸 `cargo build` 即可工作。
# 此 wrapper 仅在需要指向其他安装位置（如 PDFIUM_INSTALL_DIR 自定义）时使用。

$ErrorActionPreference = "Stop"

# 切到 src-tauri（Cargo.toml 所在）
Set-Location (Join-Path $PSScriptRoot "..\src-tauri")

$USER_HOME = if ($env:HOME) { $env:HOME } else { $env:USERPROFILE }
$INSTALL_DIR = if ($env:PDFIUM_INSTALL_DIR) { $env:PDFIUM_INSTALL_DIR } else { Join-Path $USER_HOME ".cache/mbforge/pdfium" }

$env:PDFIUM_LIB_PATH = Join-Path $INSTALL_DIR "lib"
$env:PDFIUM_INCLUDE_PATH = Join-Path $INSTALL_DIR "include"

if (-not (Test-Path $env:PDFIUM_LIB_PATH)) {
    Write-Host "ERROR: PDFium not installed at $INSTALL_DIR" -ForegroundColor Red
    Write-Host "Run: pwsh -File vendor/pdfium/setup.ps1" -ForegroundColor Yellow
    exit 1
}

Write-Host "PDFIUM_LIB_PATH     = $env:PDFIUM_LIB_PATH"
Write-Host "PDFIUM_INCLUDE_PATH = $env:PDFIUM_INCLUDE_PATH"

& cargo @args
exit $LASTEXITCODE
