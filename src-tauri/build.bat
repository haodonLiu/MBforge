@echo off
REM MBForge 构建脚本 — 自动设置 PDFium 路径
REM
REM 用法: build.bat [cargo args...]
REM 示例: build.bat check
REM       build.bat test --lib

set SCRIPT_DIR=%~dp0
set VENDOR_LIB=%SCRIPT_DIR%vendor\pdfium\release\lib
set VENDOR_INCLUDE=%SCRIPT_DIR%vendor\pdfium\release\include

if exist "%VENDOR_LIB%" if exist "%VENDOR_INCLUDE%" (
    set PDFIUM_LIB_PATH=%VENDOR_LIB%
    set PDFIUM_INCLUDE_PATH=%VENDOR_INCLUDE%
    echo PDFium: using vendor at %VENDOR_LIB%
) else (
    echo WARNING: vendor\pdfium\release not found. Run vendor\pdfium\setup.ps1 first.
)

cargo %*
