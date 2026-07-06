@echo off
REM MBForge 一键安装脚本 (Windows 原生 cmd)
REM 需求：Python 3.12.x, Node >=20.19, npm, uv
REM 用法：双击或 cmd 中执行 scripts\install.bat

setlocal enabledelayedexpansion

cd /d "%~dp0\.."

echo ==========================================
echo   MBForge 一键安装 (Windows)
echo ==========================================
echo.

REM ---- 1. Python ----
where python >nul 2>nul
if errorlevel 1 (
    echo [X] Python 未安装。需要 Python 3.12.x。
    echo     下载：https://www.python.org/downloads/
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VERSION=%%v
for /f "tokens=1,2 delims=." %%a in ("!PY_VERSION!") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
if not "!PY_MAJOR!"=="3" (
    echo [X] Python 版本不符：!PY_VERSION!（要求 3.12.x）
    exit /b 1
)
if not "!PY_MINOR!"=="12" (
    echo [X] Python 版本不符：!PY_VERSION!（要求 3.12.x）。pyproject.toml 锁定 ^>=3.12,^<3.13。
    exit /b 1
)
echo [OK] Python !PY_VERSION!

REM ---- 2. Node ----
where node >nul 2>nul
if errorlevel 1 (
    echo [X] Node 未安装。需要 Node ^>=20.19（Vite 8 baseline）。
    echo     下载：https://nodejs.org/
    exit /b 1
)
for /f "tokens=1 delims=v" %%v in ('node --version') do set NODE_VERSION=%%v
for /f "tokens=1,2 delims=." %%a in ("!NODE_VERSION!") do (
    set NODE_MAJOR=%%a
    set NODE_MINOR=%%b
)
if !NODE_MAJOR! LSS 20 (
    echo [X] Node 版本过低：v!NODE_VERSION!（要求 ^>=20.19）
    exit /b 1
)
if !NODE_MAJOR! EQU 20 if !NODE_MINOR! LSS 19 (
    echo [X] Node 版本过低：v!NODE_VERSION!（要求 ^>=20.19）
    exit /b 1
)
echo [OK] Node v!NODE_VERSION!

where npm >nul 2>nul
if errorlevel 1 (
    echo [X] npm 未安装。
    exit /b 1
)
for /f "tokens=1" %%v in ('npm --version') do set NPM_VERSION=%%v
echo [OK] npm !NPM_VERSION!

REM ---- 3. uv ----
where uv >nul 2>nul
if errorlevel 1 (
    echo.
    echo [!] uv 未安装。请先安装 uv（二选一）：
    echo     winget install astral-sh.uv
    echo     pip install uv
    echo     文档：https://docs.astral.sh/uv/
    echo.
    echo 安装完 uv 后重新运行本脚本。
    exit /b 1
)
for /f "tokens=2" %%v in ('uv --version') do set UV_VERSION=%%v
echo [OK] uv !UV_VERSION!

REM ---- 4. Python 依赖 ----
echo.
echo [1/2] 安装 Python 依赖（uv sync --dev）...
echo       PyTorch CUDA 12.8 + RDKit + OpenKB + MolScribe 等
echo       首次安装预计 5-15 分钟
echo.
uv sync --dev --index-strategy unsafe-best-match
if errorlevel 1 (
    echo [X] uv sync 失败
    exit /b 1
)

REM ---- 5. 前端依赖 ----
echo.
echo [2/2] 安装前端依赖（npm install）...
echo.
cd frontend
call npm install
if errorlevel 1 (
    echo [X] npm install 失败
    exit /b 1
)
cd ..

REM ---- 完成 ----
echo.
echo ==========================================
echo [OK] 安装完成
echo ==========================================
echo.
echo 下一步：
echo.
echo   REM 启动后端 + 前端（推荐）
echo   python start.py
echo.
echo   REM 或分别启动
echo   uv run uvicorn mbforge.app:app --host 127.0.0.1 --port 18792
echo   cd frontend ^&^& npm run dev
echo.
echo   REM 桌面 GUI
echo   uv run python -m mbforge --gui
echo.
echo   REM 验证
echo   uv run pytest tests/ -v
echo.

endlocal