# PDFium 二进制文件下载脚本
# 用于 LiteParse 依赖的 PDFium 渲染引擎
#
# 用法: cd src-tauri && powershell -File vendor/pdfium/setup.ps1

$ErrorActionPreference = "Stop"

$RELEASE_TAG = "chromium/7857"
$ASSET = "pdfium-win-x64.tgz"
$URL = "https://github.com/bblanchon/pdfium-binaries/releases/download/$($RELEASE_TAG -replace '/', '%2F')/$ASSET"

$VENDOR_DIR = Join-Path $PSScriptRoot "release"
$TMP_FILE = Join-Path $env:TEMP "pdfium-download.tgz"

Write-Host "Downloading PDFium from: $URL"
Invoke-WebRequest -Uri $URL -OutFile $TMP_FILE -UseBasicParsing

Write-Host "Extracting to: $VENDOR_DIR"
if (Test-Path $VENDOR_DIR) { Remove-Item -Recurse -Force $VENDOR_DIR }

# 解压 tgz
tar -xzf $TMP_FILE -C $PSScriptRoot
Rename-Item (Join-Path $PSScriptRoot "bin") -NewName "bin" -ErrorAction SilentlyContinue

Remove-Item $TMP_FILE -Force

Write-Host "PDFium installed successfully!"
Write-Host "  lib: $VENDOR_DIR\lib\pdfium.dll.lib"
Write-Host "  dll: $VENDOR_DIR\bin\pdfium.dll"
Write-Host "  include: $VENDOR_DIR\include\"
