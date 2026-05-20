@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo [INFO] MBForge 一键配置脚本
echo.

:: ---------- 1. 检查 uv ----------
where uv >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [FAIL] 未找到 uv，请先安装: curl -LsSf https://astral.sh/uv/install.sh ^| sh
    exit /b 1
)
for /f "tokens=*" %%i in ('uv --version') do echo [OK] %%i

:: ---------- 2. 创建虚拟环境 ----------
if not exist ".venv" (
    echo [INFO] 创建虚拟环境 (Python 3.12^) ...
    uv venv .venv --python 3.12
    echo [OK] 虚拟环境已创建
) else (
    echo [OK] 虚拟环境已存在
)

:: ---------- 3. 安装依赖 ----------
echo [INFO] 安装依赖 (uv sync^) ...
uv sync --dev
if %ERRORLEVEL% neq 0 (
    echo [FAIL] uv sync 失败
    exit /b 1
)
echo [OK] 主依赖安装完成

:: ---------- 4. 补装 openSAR (csar) ----------
.venv\Scripts\python.exe -c "import csar" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [INFO] 安装 openSAR (csar^) ...
    uv pip install -e openSAR/ --python .venv\Scripts\python.exe
    echo [OK] csar 已安装
) else (
    echo [OK] csar 已安装
)

:: ---------- 5. 配置 .env ----------
if not exist ".env" (
    echo [INFO] 从模板创建 .env ...
    copy .env.template .env >nul
    echo [OK] .env 已创建，请编辑填入你的 API Key
) else (
    echo [OK] .env 已存在
)

:: ---------- 6. 验证 ----------
echo.
echo [INFO] 验证安装 ...

.venv\Scripts\python.exe -c "import torch; v=torch.__version__; print(f'[OK] PyTorch {v}, CUDA={torch.cuda.is_available()}')" 2>nul
if %ERRORLEVEL% neq 0 echo [WARN] PyTorch CUDA 不可用

.venv\Scripts\python.exe -c "import lxml.etree; print(f'[OK] lxml {lxml.etree.__version__}')" 2>nul
if %ERRORLEVEL% neq 0 echo [WARN] lxml 未安装

.venv\Scripts\python.exe -c "import csar; print(f'[OK] csar {csar.__version__}')" 2>nul
if %ERRORLEVEL% neq 0 echo [WARN] csar 未安装

.venv\Scripts\python.exe -c "import mbforge; print(f'[OK] mbforge {mbforge.__version__}')" 2>nul
if %ERRORLEVEL% neq 0 echo [WARN] mbforge 未安装

echo.
echo ========================================
echo   配置完成! 运行 mbforge 启动应用
echo ========================================

endlocal
