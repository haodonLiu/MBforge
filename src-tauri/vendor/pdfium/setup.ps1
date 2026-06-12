# PDFium 二进制下载与安装脚本
# 用于 LiteParse 依赖的 PDFium 渲染引擎
#
# 行为：
#   1. 优先使用本地缓存 $CACHE_PATH（默认系统临时目录/pdfium-<platform>.tgz）
#   2. 缓存不存在则从 run-llama/pdfium-binaries/releases/latest 下载到缓存
#   3. 解压到用户缓存目录 $INSTALL_DIR（默认 $HOME/.cache/mbforge/pdfium/）
#      跨平台对齐：Windows / Linux / macOS 都用 $HOME/.cache/
#
# 环境变量：
#   PDFIUM_CACHE_PATH   覆盖默认缓存文件路径
#   PDFIUM_INSTALL_DIR  覆盖默认解压目录
#
# 用法: cd src-tauri && powershell -File vendor/pdfium/setup.ps1
#   必须以 UTF-8 BOM 编码（PowerShell 5.1 才能正确解析含中文注释的脚本）

$ErrorActionPreference = "Stop"

# 用户主目录：Windows 下 $HOME 不一定存在，回退 USERPROFILE
$USER_HOME = if ($env:HOME) { $env:HOME } else { $env:USERPROFILE }

# 当前平台对应的 tgz asset 名（与 liteparse-pdfium-sys::pdfium_asset_stem 保持一致）
$ASSET_STEM = switch ($env:PROCESSOR_ARCHITECTURE) {
    "AMD64" { "pdfium-win-x64" }
    "ARM64" { "pdfium-win-arm64" }
    "x86"   { "pdfium-win-x86" }
    default { "pdfium-win-x64" }
}

# 默认缓存：系统临时目录/pdfium-<platform>.tgz
if ($env:PDFIUM_CACHE_PATH) {
    $CACHE_PATH = $env:PDFIUM_CACHE_PATH
} else {
    $CACHE_PATH = Join-Path ([System.IO.Path]::GetTempPath()) "$ASSET_STEM.tgz"
}

# 默认解压目录：$HOME/.cache/mbforge/pdfium/
if ($env:PDFIUM_INSTALL_DIR) {
    $INSTALL_DIR = $env:PDFIUM_INSTALL_DIR
} else {
    $INSTALL_DIR = Join-Path $USER_HOME ".cache/mbforge/pdfium"
}

$URL = "https://github.com/run-llama/pdfium-binaries/releases/latest/download/$ASSET_STEM.tgz"

# 取得缓存（已存在则跳过下载）
if (Test-Path $CACHE_PATH) {
    Write-Host "Using cached PDFium: $CACHE_PATH"
} else {
    Write-Host "Downloading PDFium from: $URL"
    Write-Host "Saving to: $CACHE_PATH"
    Invoke-WebRequest -Uri $URL -OutFile $CACHE_PATH -UseBasicParsing
}

# 优先用 System32 tar.exe (bsdtar，Windows 原生)，避免 PATH 里的 GNU tar 把 C:\ 当远程主机
$TAR = 'C:\Windows\System32\tar.exe'
if (-not (Test-Path -LiteralPath $TAR)) { $TAR = "tar.exe" }

# 下载/缓存就绪后再清理旧安装 + 解压；tar 失败则停止并保留旧安装
if (Test-Path $INSTALL_DIR) { Remove-Item -Recurse -Force $INSTALL_DIR }
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null
& $TAR -xzf $CACHE_PATH -C $INSTALL_DIR
if ($LASTEXITCODE -ne 0) {
    throw "tar failed with exit code $LASTEXITCODE"
}

Write-Host "PDFium installed successfully!"
Write-Host "  install: $INSTALL_DIR"
Write-Host "  lib:     $INSTALL_DIR\lib\pdfium.dll.lib"
Write-Host "  dll:     $INSTALL_DIR\bin\pdfium.dll"
Write-Host "  include: $INSTALL_DIR\include\"
Write-Host "  cache:   $CACHE_PATH"
