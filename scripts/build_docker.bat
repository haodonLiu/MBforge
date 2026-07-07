@echo off
REM MBForge Docker 镜像构建脚本 (Windows 原生 cmd)
REM 需求：Docker Desktop，可选 NVIDIA GPU + nvidia-container-toolkit

setlocal enabledelayedexpansion

cd /d "%~dp0\.."

if "%TAG%"=="" set TAG=mbforge:dev

echo ==========================================
echo   MBForge Docker 构建
echo   TAG: %TAG%
echo ==========================================
echo.

REM ---- Docker 检查 ----
where docker >nul 2>nul
if errorlevel 1 (
    echo [X] Docker 未安装。下载：https://www.docker.com/products/docker-desktop/
    exit /b 1
)
for /f "tokens=3 delims= " %%v in ('docker --version') do set DOCKER_VERSION=%%v
echo [OK] Docker %DOCKER_VERSION%

REM ---- 构建镜像 ----
echo.
echo [1/2] 构建镜像（首次 10-20 分钟）...
echo.
docker build --build-arg PYTHON_VERSION=3.12 --build-arg CUDA_VERSION=12.8.0 -t "%TAG%" -f Dockerfile .

if errorlevel 1 (
    echo [X] docker build 失败
    exit /b 1
)

REM ---- GPU 检测 ----
set GPU_FLAG=
where nvidia-smi >nul 2>nul
if not errorlevel 1 (
    docker info 2>nul | findstr /C:"nvidia" >nul
    if not errorlevel 1 (
        set GPU_FLAG=--gpus all
        echo [OK] 检测到 NVIDIA GPU + nvidia-container-toolkit
    ) else (
        echo [!] nvidia-smi 在，但 Docker 看不到 NVIDIA runtime
    )
) else (
    echo [!] 未检测到 NVIDIA GPU，将以 CPU 模式运行
)

REM ---- 镜像大小 ----
echo.
for /f "tokens=*" %%s in ('docker images "%TAG%" --format "{{.Size}}"') do (
    echo [OK] 镜像大小: %%s
    goto :size_done
)
:size_done

echo.
echo ==========================================
echo [OK] 构建完成
echo ==========================================
echo.
echo 运行：
echo.
echo   REM GPU 模式
echo   docker run --rm %GPU_FLAG% -p 18792:18792 %TAG%
echo.
echo   REM 数据持久化
echo   docker run --rm %GPU_FLAG% -p 18792:18792 ^
echo     -v mbforge-config:/root/.config/MBForge ^
echo     -v mbforge-cache:/root/.cache ^
echo     %TAG%
echo.
echo 访问：http://localhost:18792
echo.

endlocal