@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════╗
echo ║     MBForge 一键配置（交互式）           ║
echo ╚══════════════════════════════════════════╝
echo.

set "PYTHON=.venv\Scripts\python.exe"
set "SCRIPT_DIR=%~dp0"

:: ═══ 01 基础环境 ═══
echo ═══ 基础环境检查 ═══
where uv >nul 2>&1 || (echo [FAIL] 未找到 uv & exit /b 1)
for /f "tokens=*" %%i in ('uv --version') do echo [OK] %%i

if not exist ".venv" (
    uv venv .venv --python 3.12
    echo [OK] 虚拟环境已创建
) else (echo [OK] 虚拟环境已存在)

uv sync --dev
%PYTHON% -c "import csar" >nul 2>&1 || uv pip install -e openSAR/ --python .venv\Scripts\python.exe
echo [OK] 依赖安装完成

:: ═══ 02 UniParser ═══
echo.
echo ═══ UniParser 配置 ═══
set "UNIPARSER_HOST="
set "UNIPARSER_KEY="
set /p "UP=是否配置 UniParser？[Y/n]: "
if /i not "%UP%"=="n" (
    set /p "UNIPARSER_HOST=服务地址 [https://your-server.com]: "
    if "!UNIPARSER_HOST!"=="" set "UNIPARSER_HOST=https://your-server.com"
    set /p "UNIPARSER_KEY=API Key: "
)

:: ═══ 03 Ollama ═══
echo.
echo ═══ Ollama 检测 ═══
set "OLLAMA_AVAILABLE=0"
where ollama >nul 2>&1 && (set "OLLAMA_AVAILABLE=1" & echo [OK] 检测到 Ollama)

:: ═══ 04 LLM ═══
echo.
echo ═══ LLM 配置 ═══
echo   1^) OpenAI 兼容 API
echo   2^) Anthropic
if "%OLLAMA_AVAILABLE%"=="1" echo   3^) Ollama
set /p "LC=选择 [1]: "
if "%LC%"=="" set "LC=1"

set "LLM_PROVIDER=openai_compatible"
set "LLM_BASE_URL=https://api.siliconflow.cn/v1"
set "LLM_API_KEY="
set "LLM_MODEL=Qwen/Qwen2.5-7B-Instruct"

if "%LC%"=="2" (
    set "LLM_PROVIDER=anthropic"
    set "LLM_BASE_URL=https://api.minimaxi.com/anthropic"
    set "LLM_MODEL=MiniMax-M2.7"
)
if "%LC%"=="3" if "%OLLAMA_AVAILABLE%"=="1" (
    set "LLM_PROVIDER=ollama"
    set "LLM_BASE_URL=http://localhost:11434/v1"
    set "LLM_API_KEY=ollama"
    set "LLM_MODEL=qwen2.5:7b"
)

set /p "LLM_BASE_URL=API Base URL [!LLM_BASE_URL!]: "
if "!LLM_BASE_URL!"=="" set "LLM_BASE_URL=!LLM_BASE_URL!"
set /p "LLM_API_KEY=API Key: "
set /p "LLM_MODEL=模型 [!LLM_MODEL!]: "
if "!LLM_MODEL!"=="" set "LLM_MODEL=!LLM_MODEL!"
echo [OK] LLM: %LLM_PROVIDER% / %LLM_MODEL%

:: ═══ 05 Embedding / Rerank ═══
echo.
echo ═══ 模型配置 ═══
set "EMBED_MODEL=BAAI/bge-small-zh-v1.5"
set "RERANK_MODEL=BAAI/bge-reranker-base"

echo Embedding: 1^) bge-small  2^) bge-large  3^) Qwen3-Embedding
set /p "EC=选择 [1]: "
if "%EC%"=="2" set "EMBED_MODEL=BAAI/bge-large-zh-v1.5"
if "%EC%"=="3" set "EMBED_MODEL=Qwen/Qwen3-Embedding-0.6B"

echo Rerank: 1^) bge-base  2^) bge-v2-m3  3^) Qwen3-Reranker
set /p "RC=选择 [1]: "
if "%RC%"=="2" set "RERANK_MODEL=BAAI/bge-reranker-v2-m3"
if "%RC%"=="3" set "RERANK_MODEL=Qwen/Qwen3-Reranker-0.6B"

:: ═══ 07 写入 .env ═══
echo.
echo ═══ 写入配置 ═══
if exist ".env" copy .env .env.bak >nul 2>&1

(
echo # UniParser
echo UNIPARSER_HOST=%UNIPARSER_HOST%
echo UNIPARSER_API_KEY=%UNIPARSER_KEY%
echo.
echo # LLM
echo MBFORGE_LLM_PROVIDER=%LLM_PROVIDER%
echo MBFORGE_LLM_BASE_URL=%LLM_BASE_URL%
echo MBFORGE_LLM_API_KEY=%LLM_API_KEY%
echo MBFORGE_LLM_MODEL=%LLM_MODEL%
echo MBFORGE_LLM_MAX_TOKENS=4096
echo MBFORGE_LLM_TEMPERATURE=0.7
echo MBFORGE_LLM_TOP_P=0.9
echo.
echo # Embedding
echo MBFORGE_EMBED_PROVIDER=sentence_transformers
echo MBFORGE_EMBED_MODEL=%EMBED_MODEL%
echo MBFORGE_EMBED_DEVICE=cpu
echo.
echo # Rerank
echo MBFORGE_RERANK_MODEL=%RERANK_MODEL%
echo MBFORGE_RERANK_DEVICE=cpu
) > .env
echo [OK] .env 已写入

:: ═══ 08 验证 ═══
echo.
echo ═══ 验证 ═══
%PYTHON% -c "import torch; print(f'PyTorch OK, CUDA={torch.cuda.is_available()}')" 2>nul && echo [OK] PyTorch || echo [WARN] PyTorch
%PYTHON% -c "import mbforge; print('mbforge OK')" 2>nul && echo [OK] mbforge || echo [WARN] mbforge

echo.
echo ╔══════════════════════════════════════════╗
echo ║  配置完成! 运行 uv run mbforge 启动应用  ║
echo ╚══════════════════════════════════════════╝

endlocal
