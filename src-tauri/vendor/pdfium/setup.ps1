# PDFium 二进制下载与安装脚本
# 用于 LiteParse 依赖的 PDFium 渲染引擎
#
# 行为：
#   1. 优先使用本地缓存 $CACHE_PATH（默认项目根/pdfium-win-x64.tgz）
#   2. 缓存不存在则从 run-llama/pdfium-binaries/releases/latest 下载到缓存
#   3. 解压到 vendor/pdfium/release/ 供 Rust 编译链接
#
# 环境变量：
#   PDFIUM_CACHE_PATH  覆盖默认缓存文件路径
#
# 用法: cd src-tauri && powershell -File vendor/pdfium/setup.ps1

$ErrorActionPreference = "Stop"

# 默认缓存：项目根/pdfium-win-x64.tgz
if ($env:PDFIUM_CACHE_PATH) {
    $CACHE_PATH = $env:PDFIUM_CACHE_PATH
} else {
    $CACHE_PATH = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\..\..\pdfium-win-x64.tgz"))
}

$URL = "https://github.com/run-llama/pdfium-binaries/releases/latest/download/pdfium-win-x64.tgz"
$VENDOR_DIR = Join-Path $PSScriptRoot "release"

# 取得缓存（已存在则跳过下载）
if (Test-Path $CACHE_PATH) {
    Write-Host "Using cached PDFium: $CACHE_PATH"
} else {
    Write-Host "Downloading PDFium from: $URL"
    Write-Host "Saving to: $CACHE_PATH"
    Invoke-WebRequest -Uri $URL -OutFile $CACHE_PATH -UseBasicParsing
}

# 解压到 vendor/pdfium/release/
if (Test-Path $VENDOR_DIR) { Remove-Item -Recurse -Force $VENDOR_DIR }
New-Item -ItemType Directory -Force -Path $VENDOR_DIR | Out-Null
tar -xzf $CACHE_PATH -C $VENDOR_DIR

Write-Host "PDFium installed successfully!"
Write-Host "  lib:     $VENDOR_DIR\lib\pdfium.dll.lib"
Write-Host "  dll:     $VENDOR_DIR\bin\pdfium.dll"
Write-Host "  include: $VENDOR_DIR\include\"
Write-Host "  cache:   $CACHE_PATH"
